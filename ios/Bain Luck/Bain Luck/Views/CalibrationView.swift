import Charts
import Combine
import SwiftUI

// MARK: - Main View

struct CalibrationView: View {
    @StateObject private var vm = CalibrationViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading calibration data...")
            } else if let error = vm.error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.secondary)
                    Text(error).font(.subheadline).foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load() } }.buttonStyle(.borderedProminent)
                }
            } else { scrollContent }
        }
        .navigationTitle("Calibration")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await vm.load() }
    }

    private var scrollContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                heroSection; statCardsSection; cohortPicker
                calibrationChartSection; sourceComparisonSection
                tradingActivitySection; categoryBreakdownSection
                benchmarkSection
            }
            .padding(.horizontal).padding(.bottom, 32)
        }
    }

    // MARK: - Hero

    private var heroSection: some View {
        VStack(spacing: 6) {
            Text("Do Markets Predict?").font(.title2.weight(.bold))
            Text("How well prediction market prices correspond to real-world outcomes across \(vm.formattedOutcomes) resolved predictions.")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Text("March\u{2013}May 2026 \u{00B7} Updated hourly")
                .font(.caption2).foregroundStyle(.tertiary)
        }.padding(.top, 8)
    }

    // MARK: - Stat Cards

    private var statCardsSection: some View {
        VStack(spacing: 10) {
            mceHeroCard
            HStack(spacing: 10) {
                miniStatCard("OUTCOMES", vm.formattedOutcomes, "checkmark.circle.fill", .blue)
                miniStatCard("MARKETS", vm.formattedMarkets, "chart.bar.fill", .purple)
                miniStatCard("BRIER", String(format: "%.3f", vm.brier), "target", .orange)
            }
        }
    }

    private var mceHeroCard: some View {
        VStack(spacing: 4) {
            Text("MEAN CALIBRATION ERROR")
                .font(.caption2.weight(.medium)).foregroundStyle(.secondary).tracking(0.5)
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(String(format: "%.1f", vm.mce * 100))
                    .font(.system(size: 44, weight: .bold, design: .monospaced))
                    .foregroundStyle(vm.mceColor)
                Text("pp").font(.title3.weight(.medium)).foregroundStyle(.secondary)
            }
            if let ciLo = vm.data?.mceCiLower, let ciHi = vm.data?.mceCiUpper {
                Text("95% CI: \(String(format: "%.1f", ciLo))\u{2013}\(String(format: "%.1f", ciHi))pp")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
            Text(vm.mceQualityLabel).font(.caption2.weight(.medium)).foregroundStyle(vm.mceColor)
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(vm.mceColor.opacity(0.12), in: Capsule())
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

    private var cohortPicker: some View {
        Picker("Cohort", selection: $vm.cohort) {
            Text("All").tag(CalibrationCohort.all)
            Text("Closing Line").tag(CalibrationCohort.closing)
            Text("Opening Price").tag(CalibrationCohort.opening)
        }.pickerStyle(.segmented)
    }

    // MARK: - Calibration Chart

    private var calibrationChartSection: some View {
        cardSection("Calibration Curve",
                    sub: "Points on the diagonal = perfect. Above = outcomes happened more than predicted. Point size = sample count.") {
            calibrationChart(points: vm.chartPoints, color: vm.cohortColor, height: 300)
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
                    .foregroundStyle(color).symbolSize(p.size)
            }
            if let s2 = secondSeries {
                ForEach(s2.pts) { p in
                    LineMark(x: .value("P", p.predicted), y: .value("A", p.actual), series: .value("S", "secondary"))
                        .foregroundStyle(s2.color).lineStyle(StrokeStyle(lineWidth: 2))
                    PointMark(x: .value("P", p.predicted), y: .value("A", p.actual))
                        .foregroundStyle(s2.color).symbolSize(p.size * 0.7)
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
        cardSection("Source Comparison", sub: "How each data source performs independently.") {
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    Text("Source").frame(maxWidth: .infinity, alignment: .leading)
                    Text("N").frame(width: 60, alignment: .trailing)
                    Text("MCE").frame(width: 52, alignment: .trailing)
                    Text("Brier").frame(width: 55, alignment: .trailing)
                }
                .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                .padding(.horizontal, 12).padding(.vertical, 8)
                Divider()
                ForEach(vm.sourceRows) { row in
                    sourceRow(row)
                    if row.name != vm.sourceRows.last?.name { Divider().padding(.leading, 12) }
                }
                Divider()
                HStack(spacing: 0) {
                    Text("Combined").font(.caption.weight(.semibold)).frame(maxWidth: .infinity, alignment: .leading)
                    Text(vm.formattedOutcomes).frame(width: 60, alignment: .trailing).monospacedDigit()
                    Text(String(format: "%.1f", vm.mce * 100)).frame(width: 52, alignment: .trailing)
                        .monospacedDigit().foregroundStyle(vm.mceColor).fontWeight(.semibold)
                    Text(String(format: "%.3f", vm.brier)).frame(width: 55, alignment: .trailing).monospacedDigit()
                }
                .font(.caption).padding(.horizontal, 12).padding(.vertical, 10)
                .background(Color.systemGray5.opacity(0.5))
            }
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func sourceRow(_ row: CalibrationTableRow) -> some View {
        HStack(spacing: 0) {
            HStack(spacing: 6) {
                Circle().fill(sourceColor(row.name)).frame(width: 8, height: 8)
                Text(row.name).lineLimit(1)
            }.frame(maxWidth: .infinity, alignment: .leading)
            Text(fmtN(row.n)).frame(width: 60, alignment: .trailing).monospacedDigit()
            Text(String(format: "%.1f", row.mce * 100)).frame(width: 52, alignment: .trailing)
                .monospacedDigit().foregroundStyle(mceColor(row.mce * 100)).fontWeight(.semibold)
            Text(String(format: "%.3f", row.brier)).frame(width: 55, alignment: .trailing).monospacedDigit()
        }
        .font(.caption).padding(.horizontal, 12).padding(.vertical, 10)
    }

    // MARK: - Trading Activity

    @ViewBuilder
    private var tradingActivitySection: some View {
        let moved = vm.movedBuckets, unchanged = vm.unchangedBuckets
        let movedN = moved.reduce(0) { $0 + $1.n }, unchangedN = unchanged.reduce(0) { $0 + $1.n }
        if movedN > 0 && unchangedN > 0 {
            let movedMCE = vm.computeMCE(moved), unchangedMCE = vm.computeMCE(unchanged)
            cardSection("Does Trading Activity Matter?",
                        sub: "Price moved (active trading) vs. price unchanged from listing.") {
                calibrationChart(points: moved, color: .green, height: 220,
                                 secondSeries: (pts: unchanged, color: .red))
                HStack(spacing: 10) {
                    tradingCard("Active Trading", movedMCE, movedN, .green)
                    tradingCard("Opening Price", unchangedMCE, unchangedN, .red)
                }
                if movedMCE > 0 && unchangedMCE > 0 {
                    Text("Markets with active trading are \(String(format: "%.1f", unchangedMCE / movedMCE))x more accurately calibrated.")
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: .infinity)
                }
            }
        }
    }

    private func tradingCard(_ label: String, _ mce: Double, _ count: Int, _ color: Color) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) { Circle().fill(color).frame(width: 8, height: 8); Text(label).font(.caption2.weight(.medium)) }
            Text(String(format: "%.1fpp", mce * 100)).font(.callout.weight(.bold).monospacedDigit()).foregroundStyle(color)
            Text("\(fmtN(count)) outcomes").font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(color.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Category Breakdown

    private var categoryBreakdownSection: some View {
        cardSection("By Category", sub: "Categories with 50+ resolved outcomes.") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(Array(vm.categoryRows.enumerated()), id: \.element.name) { idx, row in
                    categoryCard(row, idx)
                }
            }
        }
    }

    private func categoryCard(_ row: CalibrationTableRow, _ idx: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Circle().fill(Self.catColors[idx % Self.catColors.count]).frame(width: 8, height: 8)
                Text(row.name).font(.caption.weight(.semibold)).lineLimit(1)
            }
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(String(format: "%.1f", row.mce * 100))
                    .font(.title3.weight(.bold).monospacedDigit()).foregroundStyle(mceColor(row.mce * 100))
                Text("pp").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Text(fmtN(row.n)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
        .padding(10).background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Benchmark

    private var benchmarkSection: some View {
        cardSection("How We Compare", sub: "Our MCE compared to published calibration benchmarks.") {
            VStack(spacing: 8) {
                benchmarkRow("Bain Luck", vm.mce * 100, "\(vm.formattedOutcomes) outcomes", true)
                benchmarkRow("Metaculus", 2.5, "Self-reported", false)
                benchmarkRow("Iowa Electronic Markets", 1.5, "Berg et al. 2008", false)
                benchmarkRow("Academic consensus", 3.5, "Arrow et al. 2008 (2\u{2013}5pp)", false)
            }
            Text("Lower is better. Most prediction markets achieve 2\u{2013}5pp MCE.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }

    private func benchmarkRow(_ label: String, _ mce: Double, _ detail: String, _ highlight: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.caption.weight(highlight ? .bold : .regular))
                    .foregroundStyle(highlight ? .primary : .secondary)
                Spacer()
                Text(String(format: "%.1fpp", mce)).font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(mceColor(mce))
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(Color.systemGray5).frame(height: 6)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(highlight ? Color.blue : Color.gray.opacity(0.5))
                        .frame(width: min(geo.size.width, geo.size.width * mce / 10), height: 6)
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

    private func sourceColor(_ name: String) -> Color {
        switch name.lowercased() {
        case "odds_api", "odds api": return .blue
        case "kalshi": return .green
        case "polymarket": return .purple
        default: return .orange
        }
    }

    private func mceColor(_ mce: Double) -> Color {
        mce < 4 ? .green : mce < 8 ? .blue : .orange
    }

    private func fmtN(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fK", Double(n) / 1000) : "\(n)"
    }
}

// MARK: - ViewModel

enum CalibrationCohort: String { case closing, opening, all }

struct CalibrationChartPoint: Identifiable {
    let id = UUID()
    let predicted: Double, actual: Double, size: CGFloat, n: Int
}

struct CalibrationTableRow: Identifiable {
    let id = UUID()
    let name: String, n: Int, mce: Double, brier: Double
}

@MainActor
final class CalibrationViewModel: ObservableObject {
    @Published var data: CalibrationData?
    @Published var loading = true
    @Published var error: String?
    @Published var cohort: CalibrationCohort = .all

    private static let nf: NumberFormatter = { let f = NumberFormatter(); f.numberStyle = .decimal; return f }()

    var formattedOutcomes: String { data.map { Self.nf.string(from: NSNumber(value: $0.totalOutcomes)) ?? "\($0.totalOutcomes)" } ?? "\u{2014}" }
    var formattedMarkets: String { data.map { Self.nf.string(from: NSNumber(value: $0.totalMarkets)) ?? "\($0.totalMarkets)" } ?? "\u{2014}" }

    var filteredBuckets: [CalibrationBucket] {
        guard let buckets = data?.buckets else { return [] }
        switch cohort {
        case .closing: return buckets.filter { $0.priceMoved == true || $0.priceMoved == nil }
        case .opening: return buckets.filter { $0.priceMoved == false }
        case .all: return buckets
        }
    }

    var chartPoints: [CalibrationChartPoint] { makePoints(from: filteredBuckets) }
    var movedBuckets: [CalibrationChartPoint] { makePoints(from: (data?.buckets ?? []).filter { $0.priceMoved == true }) }
    var unchangedBuckets: [CalibrationChartPoint] { makePoints(from: (data?.buckets ?? []).filter { $0.priceMoved == false }) }

    var mce: Double { computeMCE(chartPoints) }
    var mceColor: Color { let v = mce * 100; return v < 4 ? .green : v < 8 ? .blue : .orange }
    var mceQualityLabel: String { let v = mce * 100; return v < 3 ? "Excellent" : v < 5 ? "Very Good" : v < 8 ? "Good" : "Fair" }
    var cohortColor: Color { cohort == .closing ? .green : cohort == .opening ? .red : .blue }

    var brier: Double {
        let b = filteredBuckets; let n = b.reduce(0) { $0 + $1.n }
        return n > 0 ? b.reduce(0.0) { $0 + $1.sumSqErr } / Double(n) : 0
    }

    var sourceRows: [CalibrationTableRow] { buildRows(groupedBy: \.source, from: filteredBuckets) }
    var categoryRows: [CalibrationTableRow] { buildRows(groupedBy: \.category, from: filteredBuckets).filter { $0.n >= 50 } }

    func computeMCE(_ points: [CalibrationChartPoint]) -> Double {
        guard !points.isEmpty else { return 0 }
        return points.reduce(0.0) { $0 + abs($1.actual - $1.predicted) } / Double(points.count) / 100
    }

    func load() async {
        loading = true; error = nil
        do { data = try await APIClient.shared.fetchCalibration() } catch { self.error = error.localizedDescription }
        loading = false
    }

    // MARK: - Private

    private struct AggBucket { let bucketIdx: Int; var n = 0; var winners = 0; var sumSqErr: Double = 0 }

    private func makePoints(from buckets: [CalibrationBucket]) -> [CalibrationChartPoint] {
        aggregateByBucket(buckets).map { b in
            let pred = Double(b.bucketIdx) * 10 + 5
            let act = b.n > 0 ? Double(b.winners) / Double(b.n) * 100 : pred
            return CalibrationChartPoint(predicted: pred, actual: act, size: max(30, min(200, CGFloat(b.n) / 8)), n: b.n)
        }
    }

    private func aggregateByBucket(_ buckets: [CalibrationBucket]) -> [AggBucket] {
        var byIdx: [Int: AggBucket] = [:]
        for b in buckets {
            var a = byIdx[b.bucketIdx] ?? AggBucket(bucketIdx: b.bucketIdx)
            a.n += b.n; a.winners += b.winners; a.sumSqErr += b.sumSqErr; byIdx[b.bucketIdx] = a
        }
        return (0..<10).compactMap { byIdx[$0] }.sorted { $0.bucketIdx < $1.bucketIdx }
    }

    private func buildRows(groupedBy kp: KeyPath<CalibrationBucket, String>, from buckets: [CalibrationBucket]) -> [CalibrationTableRow] {
        var groups: [String: (n: Int, winners: Int, sqErr: Double, buckets: [CalibrationBucket])] = [:]
        for b in buckets {
            let k = b[keyPath: kp]
            var g = groups[k] ?? (0, 0, 0, [])
            g.n += b.n; g.winners += b.winners; g.sqErr += b.sumSqErr; g.buckets.append(b); groups[k] = g
        }
        return groups.map { k, g in
            let agg = aggregateByBucket(g.buckets); let total = agg.reduce(0) { $0 + $1.n }
            var wErr = 0.0
            for a in agg { let m = Double(a.bucketIdx) * 0.1 + 0.05; let w = a.n > 0 ? Double(a.winners) / Double(a.n) : m; wErr += abs(w - m) * Double(a.n) }
            let dn = k.replacingOccurrences(of: "_", with: " ").capitalized
            return CalibrationTableRow(name: dn, n: g.n, mce: total > 0 ? wErr / Double(total) : 0, brier: g.n > 0 ? g.sqErr / Double(g.n) : 0)
        }.sorted { $0.n > $1.n }
    }
}
