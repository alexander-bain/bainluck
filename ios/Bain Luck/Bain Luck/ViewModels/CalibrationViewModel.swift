import Combine
import Foundation
import SwiftUI

@MainActor
final class CalibrationViewModel: ObservableObject {
    @Published private(set) var data: CalibrationData?
    @Published private(set) var loading = true
    @Published private(set) var error: String?
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
