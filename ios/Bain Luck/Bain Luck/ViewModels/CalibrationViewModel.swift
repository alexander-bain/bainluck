import Combine
import Foundation
import SwiftUI

@MainActor
final class CalibrationViewModel: ObservableObject {
    @Published private(set) var data: CalibrationData?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

    private static let nf: NumberFormatter = { let f = NumberFormatter(); f.numberStyle = .decimal; return f }()

    var formattedOutcomes: String { data.map { Self.nf.string(from: NSNumber(value: $0.totalOutcomes)) ?? "\($0.totalOutcomes)" } ?? "\u{2014}" }
    var formattedMarkets: String { data.map { Self.nf.string(from: NSNumber(value: $0.totalMarkets)) ?? "\($0.totalMarkets)" } ?? "\u{2014}" }

    var filteredBuckets: [CalibrationBucket] {
        data?.buckets ?? []
    }

    var chartPoints: [CalibrationChartPoint] { makePoints(from: filteredBuckets) }
    var movedBuckets: [CalibrationChartPoint] { makePoints(from: (data?.buckets ?? []).filter { $0.priceMoved == true }) }
    var unchangedBuckets: [CalibrationChartPoint] { makePoints(from: (data?.buckets ?? []).filter { $0.priceMoved == false }) }

    var mce: Double { computeMCE(chartPoints) }
    var mceColor: Color { let v = mce * 100; return v < 4 ? .green : v < 8 ? .blue : .orange }
    var mceQualityLabel: String { let v = mce * 100; return v < 3 ? "Excellent" : v < 5 ? "Very Good" : v < 8 ? "Good" : "Fair" }
    var cohortColor: Color { .blue }

    var brier: Double {
        let b = filteredBuckets; let n = b.reduce(0) { $0 + $1.n }
        return n > 0 ? b.reduce(0.0) { $0 + $1.sumSqErr } / Double(n) : 0
    }

    var sourceRows: [CalibrationTableRow] {
        buildRows(from: filteredBuckets, key: { $0.source }, displayName: Self.sourceDisplayName)
    }
    var categoryRows: [CalibrationTableRow] {
        buildRows(from: filteredBuckets, key: { Self.normalizedCategory($0.category) }, displayName: Self.categoryDisplayName)
            .filter { $0.n >= 100 }
    }
    var topCategoryRows: [CalibrationTableRow] { Array(categoryRows.prefix(10)) }
    var bestCategoryRow: CalibrationTableRow? {
        categoryRows.filter { $0.n >= 1000 }.min { $0.mce < $1.mce } ?? categoryRows.min { $0.mce < $1.mce }
    }
    var worstCategoryRow: CalibrationTableRow? {
        categoryRows.filter { $0.n >= 1000 }.max { $0.mce < $1.mce } ?? categoryRows.max { $0.mce < $1.mce }
    }

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

    private func buildRows(
        from buckets: [CalibrationBucket],
        key: (CalibrationBucket) -> String,
        displayName: (String) -> String
    ) -> [CalibrationTableRow] {
        var groups: [String: (n: Int, winners: Int, sqErr: Double, buckets: [CalibrationBucket])] = [:]
        for b in buckets {
            let k = key(b)
            var g = groups[k] ?? (0, 0, 0, [])
            g.n += b.n; g.winners += b.winners; g.sqErr += b.sumSqErr; g.buckets.append(b); groups[k] = g
        }
        return groups.map { k, g in
            let agg = aggregateByBucket(g.buckets); let total = agg.reduce(0) { $0 + $1.n }
            var wErr = 0.0
            for a in agg { let m = Double(a.bucketIdx) * 0.1 + 0.05; let w = a.n > 0 ? Double(a.winners) / Double(a.n) : m; wErr += abs(w - m) * Double(a.n) }
            return CalibrationTableRow(name: displayName(k), n: g.n, mce: total > 0 ? wErr / Double(total) : 0, brier: g.n > 0 ? g.sqErr / Double(g.n) : 0)
        }.sorted { $0.n > $1.n }
    }

    private static func normalizedCategory(_ category: String) -> String {
        if let mapped = sportKeyMap[category] { return mapped }
        let base = category.split(separator: "_").first.map(String.init) ?? category
        if base == "americanfootball" { return "football" }
        if base == "icehockey" { return "hockey" }
        return categoryDisplayNames[base] == nil ? category : base
    }

    private static func categoryDisplayName(_ category: String) -> String {
        categoryDisplayNames[category] ?? category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func sourceDisplayName(_ source: String) -> String {
        sourceDisplayNames[source] ?? source.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static let sportKeyMap: [String: String] = [
        "basketball_nba": "basketball", "basketball_ncaab": "basketball",
        "basketball_wnba": "basketball", "basketball_nbl": "basketball",
        "basketball_wncaab": "basketball", "basketball_euroleague": "basketball",
        "americanfootball_nfl": "football", "americanfootball_ncaaf": "football",
        "baseball_mlb": "baseball", "icehockey_nhl": "hockey",
        "soccer_epl": "soccer", "soccer_usa_mls": "soccer",
        "soccer_uefa_champs_league": "soccer", "soccer_spain_la_liga": "soccer",
        "soccer_germany_bundesliga": "soccer", "soccer_italy_serie_a": "soccer",
        "soccer_france_ligue_one": "soccer", "soccer_uefa_europa_league": "soccer",
        "mma_mixed_martial_arts": "mma", "golf_pga": "golf", "golf_lpga": "golf",
        "cricket_ipl": "cricket", "cricket_test_match": "cricket",
    ]

    private static let categoryDisplayNames: [String: String] = [
        "basketball": "Basketball", "baseball": "Baseball", "hockey": "Hockey",
        "football": "Football", "soccer": "Soccer", "golf": "Golf",
        "tennis": "Tennis", "mma": "MMA", "cricket": "Cricket",
        "esports": "Esports", "politics": "Politics", "geopolitics": "Geopolitics",
        "entertainment": "Entertainment", "weather": "Weather", "economics": "Economics",
        "tech": "Tech", "motorsports": "Motorsports",
    ]

    private static let sourceDisplayNames: [String: String] = [
        "kalshi": "Kalshi",
        "polymarket": "Polymarket",
        "odds_api": "Odds API",
        "odds_api_spreads": "Spreads (Odds API)",
        "odds_api_totals": "Totals (Odds API)",
        "odds_api_bookmaker": "Per-Bookmaker (Odds API)",
    ]
}
