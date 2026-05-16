import Charts
import Combine
import SwiftUI

struct CalibrationView: View {
    @StateObject private var vm = CalibrationViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading calibration data...")
            } else if let error = vm.error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load() } }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                content
            }
        }
        .navigationTitle("Calibration")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await vm.load() }
    }

    @ViewBuilder
    private var content: some View {
        ScrollView {
            VStack(spacing: 20) {
                heroSection
                cohortPicker
                statCards
                calibrationChart
                sourceTable
                categoryTable
            }
            .padding(.horizontal)
            .padding(.bottom, 32)
        }
    }

    private var heroSection: some View {
        VStack(spacing: 8) {
            Text("Do Markets Predict?")
                .font(.title2.weight(.bold))
            Text("How well prediction market prices correspond to real-world outcomes across \(vm.formattedOutcomes) resolved predictions.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top)
    }

    private var cohortPicker: some View {
        Picker("Cohort", selection: $vm.cohort) {
            Text("Closing Line").tag(CalibrationCohort.closing)
            Text("Opening Price").tag(CalibrationCohort.opening)
            Text("All").tag(CalibrationCohort.all)
        }
        .pickerStyle(.segmented)
    }

    private var statCards: some View {
        LazyVGrid(columns: [
            GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())
        ], spacing: 12) {
            statCard("Outcomes", value: vm.formattedOutcomes)
            statCard("MCE", value: String(format: "%.1fpp", vm.mce * 100))
            statCard("Brier", value: String(format: "%.3f", vm.brier))
        }
    }

    private func statCard(_ label: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title3.weight(.bold).monospacedDigit())
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
    }

    private var calibrationChart: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Calibration Curve")
                .font(.subheadline.weight(.semibold))

            Chart {
                // Perfect calibration diagonal
                RuleMark(xStart: .value("", 0), xEnd: .value("", 100),
                         yStart: .value("", 0), yEnd: .value("", 100))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .foregroundStyle(.gray.opacity(0.5))

                // Confidence band (±5pp)
                ForEach(0..<10, id: \.self) { i in
                    let midpoint = Double(i) * 10 + 5
                    AreaMark(
                        x: .value("Predicted", midpoint),
                        yStart: .value("Lower", max(0, midpoint - 5)),
                        yEnd: .value("Upper", min(100, midpoint + 5))
                    )
                    .foregroundStyle(.blue.opacity(0.06))
                }

                // Actual calibration points
                ForEach(vm.chartPoints, id: \.predicted) { point in
                    PointMark(
                        x: .value("Predicted", point.predicted),
                        y: .value("Actual", point.actual)
                    )
                    .foregroundStyle(.blue)
                    .symbolSize(point.size)

                    LineMark(
                        x: .value("Predicted", point.predicted),
                        y: .value("Actual", point.actual)
                    )
                    .foregroundStyle(.blue)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                }
            }
            .chartXScale(domain: 0...100)
            .chartYScale(domain: 0...100)
            .chartXAxisLabel("Predicted Probability (%)")
            .chartYAxisLabel("Actual Win Rate (%)")
            .frame(height: 280)
        }
        .padding()
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    private var sourceTable: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("By Source")
                .font(.subheadline.weight(.semibold))

            VStack(spacing: 0) {
                tableHeader
                ForEach(vm.sourceRows, id: \.name) { row in
                    tableRow(row)
                }
            }
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private var categoryTable: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("By Category")
                .font(.subheadline.weight(.semibold))

            VStack(spacing: 0) {
                tableHeader
                ForEach(vm.categoryRows, id: \.name) { row in
                    tableRow(row)
                }
            }
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private var tableHeader: some View {
        HStack {
            Text("").frame(maxWidth: .infinity, alignment: .leading)
            Text("N").frame(width: 50, alignment: .trailing)
            Text("MCE").frame(width: 55, alignment: .trailing)
            Text("Brier").frame(width: 55, alignment: .trailing)
        }
        .font(.caption2.weight(.medium))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func tableRow(_ row: CalibrationTableRow) -> some View {
        HStack {
            Text(row.name)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lineLimit(1)
            Text("\(row.n)")
                .frame(width: 50, alignment: .trailing)
                .monospacedDigit()
            Text(String(format: "%.1f", row.mce * 100))
                .frame(width: 55, alignment: .trailing)
                .monospacedDigit()
            Text(String(format: "%.3f", row.brier))
                .frame(width: 55, alignment: .trailing)
                .monospacedDigit()
        }
        .font(.caption)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }
}

// MARK: - ViewModel

enum CalibrationCohort: String {
    case closing, opening, all
}

struct CalibrationChartPoint {
    let predicted: Double
    let actual: Double
    let size: CGFloat
}

struct CalibrationTableRow {
    let name: String
    let n: Int
    let mce: Double
    let brier: Double
}

@MainActor
final class CalibrationViewModel: ObservableObject {
    @Published var data: CalibrationData?
    @Published var loading = true
    @Published var error: String?
    @Published var cohort: CalibrationCohort = .closing

    var formattedOutcomes: String {
        guard let d = data else { return "—" }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: d.totalOutcomes)) ?? "\(d.totalOutcomes)"
    }

    var filteredBuckets: [CalibrationBucket] {
        guard let buckets = data?.buckets else { return [] }
        switch cohort {
        case .closing:
            return buckets.filter { $0.priceMoved == true }
        case .opening:
            return buckets.filter { $0.priceMoved == false }
        case .all:
            return buckets
        }
    }

    var chartPoints: [CalibrationChartPoint] {
        let aggregated = aggregateByBucket(filteredBuckets)
        return aggregated.map { bucket in
            let predicted = Double(bucket.bucketIdx) * 10 + 5
            let winRate = bucket.n > 0 ? Double(bucket.winners) / Double(bucket.n) * 100 : predicted
            let size = max(20, min(200, CGFloat(bucket.n) / 10))
            return CalibrationChartPoint(predicted: predicted, actual: winRate, size: size)
        }
    }

    var mce: Double {
        let aggregated = aggregateByBucket(filteredBuckets)
        guard !aggregated.isEmpty else { return 0 }
        let totalN = aggregated.reduce(0) { $0 + $1.n }
        guard totalN > 0 else { return 0 }
        var weightedError = 0.0
        for b in aggregated {
            let midpoint = Double(b.bucketIdx) * 0.1 + 0.05
            let winRate = b.n > 0 ? Double(b.winners) / Double(b.n) : midpoint
            weightedError += abs(winRate - midpoint) * Double(b.n)
        }
        return weightedError / Double(totalN)
    }

    var brier: Double {
        let buckets = filteredBuckets
        let totalN = buckets.reduce(0) { $0 + $1.n }
        guard totalN > 0 else { return 0 }
        let totalSqErr = buckets.reduce(0.0) { $0 + $1.sumSqErr }
        return totalSqErr / Double(totalN)
    }

    var sourceRows: [CalibrationTableRow] {
        buildRows(groupedBy: \.source, from: filteredBuckets)
    }

    var categoryRows: [CalibrationTableRow] {
        buildRows(groupedBy: \.category, from: filteredBuckets)
            .filter { $0.n >= 50 }
    }

    func load() async {
        loading = true
        error = nil
        do {
            data = try await APIClient.shared.fetchCalibration()
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    private struct AggBucket {
        let bucketIdx: Int
        var n: Int = 0
        var winners: Int = 0
        var sumSqErr: Double = 0
    }

    private func aggregateByBucket(_ buckets: [CalibrationBucket]) -> [AggBucket] {
        var byIdx: [Int: AggBucket] = [:]
        for b in buckets {
            var agg = byIdx[b.bucketIdx] ?? AggBucket(bucketIdx: b.bucketIdx)
            agg.n += b.n
            agg.winners += b.winners
            agg.sumSqErr += b.sumSqErr
            byIdx[b.bucketIdx] = agg
        }
        return (0..<10).compactMap { byIdx[$0] }.sorted { $0.bucketIdx < $1.bucketIdx }
    }

    private func buildRows(groupedBy keyPath: KeyPath<CalibrationBucket, String>, from buckets: [CalibrationBucket]) -> [CalibrationTableRow] {
        var groups: [String: (n: Int, winners: Int, sumSqErr: Double, buckets: [CalibrationBucket])] = [:]
        for b in buckets {
            let key = b[keyPath: keyPath]
            var g = groups[key] ?? (n: 0, winners: 0, sumSqErr: 0, buckets: [])
            g.n += b.n
            g.winners += b.winners
            g.sumSqErr += b.sumSqErr
            g.buckets.append(b)
            groups[key] = g
        }
        return groups.map { key, g in
            let aggregated = aggregateByBucket(g.buckets)
            let totalN = aggregated.reduce(0) { $0 + $1.n }
            var weightedError = 0.0
            for ab in aggregated {
                let midpoint = Double(ab.bucketIdx) * 0.1 + 0.05
                let winRate = ab.n > 0 ? Double(ab.winners) / Double(ab.n) : midpoint
                weightedError += abs(winRate - midpoint) * Double(ab.n)
            }
            let mce = totalN > 0 ? weightedError / Double(totalN) : 0
            let brier = g.n > 0 ? g.sumSqErr / Double(g.n) : 0
            let displayName = key.replacingOccurrences(of: "_", with: " ").capitalized
            return CalibrationTableRow(name: displayName, n: g.n, mce: mce, brier: brier)
        }
        .sorted { $0.n > $1.n }
    }
}
