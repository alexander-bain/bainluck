import Combine
import Foundation
import SwiftUI

/// Drives the native Calibration tab. #894: this used to re-derive every headline
/// number with its OWN client-side formulas, so native disagreed with the web
/// page. It now delegates ALL math to `CalibrationMath` — the exact web-parity
/// port — and reads the payload-v2 metadata (sample gate, held-out categories,
/// corrections) straight from the API. The view renders these numbers verbatim;
/// there is no bespoke calibration arithmetic left in the view layer.
@MainActor
final class CalibrationViewModel: ObservableObject {
    @Published private(set) var data: CalibrationData?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

    /// L2-74 §C default: the WELL-TRADED view (real trading moved the price). The
    /// toggle layers thin/untraded markets back in — it never hides, both counts
    /// are always visible. View-bound, so it stays mutable.
    @Published var includeThin = false

    private static let nf: NumberFormatter = { let f = NumberFormatter(); f.numberStyle = .decimal; return f }()

    private var buckets: [CalibrationBucket] { data?.buckets ?? [] }

    // MARK: - Init

    init() {}

    /// Preloaded-payload initializer.
    ///
    /// The production path is `load()`. This exists so the surface's payload
    /// STATES — dated last-good, version mismatch, empty, parked category — can
    /// be exercised directly. Those are states the server produces and a
    /// happy-path network stub never reaches, and they are precisely where
    /// native was silently diverging from web (L2-231 Item 0).
    init(preloaded: CalibrationData) {
        self.data = preloaded
        self.loading = false
    }

    // MARK: - Loading

    func load() async {
        loading = true; error = nil
        do { data = try await APIClient.shared.fetchCalibration() } catch { self.error = error.localizedDescription }
        loading = false
    }

    /// First-load only.
    ///
    /// The surface's `.task` used to call `load()` unconditionally, and `load()`
    /// flips `loading` to true before it awaits — so re-entering the tab replaced
    /// an already-rendered curve with a spinner while the same numbers were
    /// re-fetched. Explicit refresh still goes through `load()`.
    func loadIfNeeded() async {
        guard data == nil else { return }
        await load()
    }

    // MARK: - Formatting helpers

    private static func fmt(_ n: Int) -> String { nf.string(from: NSNumber(value: n)) ?? "\(n)" }

    var formattedTotalOutcomes: String { data.map { Self.fmt($0.totalOutcomes) } ?? "\u{2014}" }
    var formattedMarkets: String { data.map { Self.fmt($0.totalMarkets) } ?? "\u{2014}" }
    var formattedCohortOutcomes: String { data == nil ? "\u{2014}" : Self.fmt(cohortN) }

    /// The population the hero claims to have analyzed.
    ///
    /// Web's hero says "{cohortN} well-traded resolved predictions ({fullN}
    /// including thinly-traded)". Native said "{totalOutcomes} resolved
    /// predictions" — the FULL total, a different number under the well-traded
    /// default, presented as the same claim. Same population, same qualifier.
    var heroPopulationText: String {
        guard data != nil else { return "\u{2014}" }
        if includeThin { return formattedCohortOutcomes }
        return "\(formattedCohortOutcomes) well-traded (\(Self.fmt(fullN)) including thinly-traded)"
    }

    // MARK: - Sample gate

    /// #997: the minimum-sample bar comes from the API (Redis-tunable) so web and
    /// native gate on the same threshold. Fall back to 1000 if a lean/older
    /// payload omits it — never regress to a noisy floor.
    var minCategoryOutcomes: Int { data?.minCategoryOutcomes ?? 1000 }

    // MARK: - Cohort metrics (ECE-first)

    /// Aggregated curve for the active cohort (well-traded by default).
    var cohortBuckets: [CalibrationMath.AggBucket] {
        let thin = includeThin
        return CalibrationMath.aggregate(buckets) { thin || $0.priceMoved != false }
    }

    /// Headline metric: n-weighted error (pp). This is what the web page leads with.
    var cohortECE: Double { CalibrationMath.ece(cohortBuckets) }
    /// Demoted secondary: equal-weighted worst-bucket-sensitivity error (pp).
    var cohortMCE: Double { CalibrationMath.mce(cohortBuckets) }
    var cohortBrier: Double {
        let thin = includeThin
        return CalibrationMath.brier(buckets) { thin || $0.priceMoved != false }
    }
    var cohortN: Int {
        let thin = includeThin
        return CalibrationMath.totalN(buckets) { thin || $0.priceMoved != false }
    }
    var fullN: Int { CalibrationMath.totalN(buckets) }
    var wellTradedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved != false } }
    var thinAddN: Int { max(0, fullN - wellTradedN) }

    var eceQualityLabel: String {
        let v = cohortECE
        return v < 3 ? "Excellent" : v < 5 ? "Very Good" : v < 8 ? "Good" : "Fair"
    }

    // MARK: - Per-source / per-category rows (from the same web-parity math)

    var sources: [String] {
        let bks = buckets
        var counts: [String: Int] = [:]
        for b in bks { counts[b.source, default: 0] += b.n }
        return counts.keys.sorted { (counts[$0] ?? 0) > (counts[$1] ?? 0) }
    }

    /// Normalized, sample-gated categories (top 15 by outcomes), matching the web.
    var categories: [String] {
        let bks = buckets
        let minN = minCategoryOutcomes
        var catMap: [String: Int] = [:]
        for b in bks { catMap[Self.normalizedCategory(b.category), default: 0] += b.n }
        return catMap
            .filter { $0.value >= minN }
            .sorted { $0.value > $1.value }
            .prefix(15)
            .map { $0.key }
    }

    var sourceRows: [CalSourceRow] {
        let bks = buckets
        let thin = includeThin
        return sources.map { src in
            let f: (CalibrationBucket) -> Bool = { $0.source == src && (thin || $0.priceMoved != false) }
            let agg = CalibrationMath.aggregate(bks, filter: f)
            let band = agg.filter { abs($0.error) <= 5 }.count
            return CalSourceRow(
                source: src, name: Self.sourceDisplayName(src),
                n: CalibrationMath.totalN(bks, filter: f),
                ece: CalibrationMath.ece(agg), mce: CalibrationMath.mce(agg),
                brier: CalibrationMath.brier(bks, filter: f),
                bucketsInBand: band, totalBuckets: agg.count
            )
        }.sorted { $0.ece < $1.ece }
    }

    var categoryRows: [CalCategoryRow] {
        let bks = buckets
        let thin = includeThin
        return categories.map { cat in
            let f: (CalibrationBucket) -> Bool = { Self.normalizedCategory($0.category) == cat && (thin || $0.priceMoved != false) }
            let agg = CalibrationMath.aggregate(bks, filter: f)
            return CalCategoryRow(
                category: cat, name: Self.categoryDisplayName(cat),
                n: CalibrationMath.totalN(bks, filter: f),
                ece: CalibrationMath.ece(agg), mce: CalibrationMath.mce(agg),
                brier: CalibrationMath.brier(bks, filter: f)
            )
        }.sorted { $0.ece < $1.ece }
    }

    var topCategoryRows: [CalCategoryRow] { Array(categoryRows.prefix(10)) }
    var bestCategoryRow: CalCategoryRow? { categoryRows.min { $0.ece < $1.ece } }
    var worstCategoryRow: CalCategoryRow? { categoryRows.max { $0.ece < $1.ece } }

    // MARK: - Trading-activity split (always the full moved/unchanged cohorts)

    var movedBuckets: [CalibrationMath.AggBucket] { CalibrationMath.aggregate(buckets) { $0.priceMoved == true } }
    var unchangedBuckets: [CalibrationMath.AggBucket] { CalibrationMath.aggregate(buckets) { $0.priceMoved == false } }
    var movedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved == true } }
    var unchangedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved == false } }
    var movedECE: Double { CalibrationMath.ece(movedBuckets) }
    var unchangedECE: Double { CalibrationMath.ece(unchangedBuckets) }

    /// L2-231 Item 2: the direction-aware, causation-free comparison the web page
    /// has rendered since L2-230. Native printed the superseded superiority claim
    /// (`unchangedECE / movedECE` labelled "more accurately calibrated") until now.
    var activity: CalibrationMath.ActivityComparison {
        CalibrationMath.describeActivity(
            movedECE: movedECE, movedN: movedN,
            unchangedECE: unchangedECE, unchangedN: unchangedN
        )
    }

    // MARK: - Freshness and population contract (Queue 297 / L2-231 Item 2)

    /// True when the served payload is a dated last-good copy rather than a
    /// current one. Web banners this; native rendered it as live.
    var isStale: Bool { data?.cache?.isStale == true }

    /// "Showing the last complete snapshot" subtitle: when it was actually built,
    /// and how old that is. Nil when the payload is current.
    ///
    /// Deliberately falls back to the payload's own `generated_at` and then to a
    /// bare "earlier": a stale payload whose envelope omits the date is still
    /// stale, and dropping the banner because we cannot format a date would
    /// present it as live — the exact failure the banner exists to prevent.
    var staleBannerDetail: String? {
        guard let cache = data?.cache, cache.isStale else { return nil }
        let built = cache.generatedAt ?? data?.generatedAt
        let whenText: String
        if let built, let date = Self.parseISO(built) {
            let f = DateFormatter()
            f.dateFormat = "MMM d, h:mm a"
            whenText = f.string(from: date)
        } else {
            whenText = "earlier"
        }
        let age = cache.ageS.map { " (\(Self.formatAge($0)) ago)" } ?? ""
        return "These numbers were built \(whenText)\(age) and are not being "
            + "refreshed right now. The curve rebuilds hourly."
    }

    /// The population contract this build renders. Bumped by the backend whenever
    /// the published population changes materially (Queue 299: q267 -> q299).
    ///
    /// This is a CONTRACT check, not a freshness check. Native cannot recompute
    /// the population, so if the payload announces one this build was not written
    /// against, the honest answer is to refuse rather than to render current-looking
    /// labels over numbers built under different rules (C111 P2 / Q297 §3).
    static let expectedPopulationVersion = "q299"

    var populationVersion: String? { data?.populationVersion }

    /// `nil` payload version means an older/lean payload that predates the
    /// contract field — rendered, but never claimed as verified.
    var populationVersionState: PopulationVersionState {
        guard let v = data?.populationVersion else { return .unverified }
        return v == Self.expectedPopulationVersion ? .matched : .mismatched(v)
    }

    enum PopulationVersionState: Equatable {
        case matched
        /// The payload names a population this build does not know how to label.
        case mismatched(String)
        /// The payload does not name its population at all.
        case unverified
    }

    /// A version-mismatched payload must not masquerade as current data. The view
    /// renders an explicit incompatible state instead of the curve.
    var isIncompatible: Bool {
        if case .mismatched = populationVersionState { return true }
        return false
    }

    var incompatibleMessage: String? {
        guard case .mismatched(let served) = populationVersionState else { return nil }
        return "This build reads calibration population \(Self.expectedPopulationVersion), "
            + "but the server published \(served). Update the app to see the current curve."
    }

    /// "3h" / "45m" / "20s" — mirrors the web page's `formatAge`. Pure, so it is
    /// `nonisolated`: the class is `@MainActor` and a static would otherwise
    /// inherit that isolation for no reason.
    nonisolated static func formatAge(_ seconds: Double) -> String {
        let s = max(0, Int(seconds.rounded()))
        if s >= 3600 { return "\(s / 3600)h" }
        if s >= 60 { return "\(s / 60)m" }
        return "\(s)s"
    }

    // MARK: - Payload-v2 trust content

    var smallSampleCategories: [SmallSampleCategory] {
        (data?.smallSampleCategories ?? []).sorted { $0.outcomes > $1.outcomes }
    }
    var smallSampleTotal: Int { smallSampleCategories.reduce(0) { $0 + $1.outcomes } }
    var corrections: [CalibrationCorrection] { data?.corrections ?? [] }

    // MARK: - Chart point conversion (rendering only)

    /// Convert aggregated buckets into chart points. Point size reflects sample
    /// count; low-n ("thin") buckets fade so the eye trusts the well-sampled ones.
    func points(from agg: [CalibrationMath.AggBucket]) -> [CalibrationChartPoint] {
        agg.map { b in
            CalibrationChartPoint(
                predicted: b.midpoint, actual: b.actual,
                size: max(30, min(200, CGFloat(b.n) / 8)),
                n: b.n, opacity: Self.opacity(forN: b.n)
            )
        }
    }

    static func opacity(forN n: Int) -> Double { n >= 200 ? 1.0 : (n >= 50 ? 0.7 : 0.4) }

    // MARK: - Colors / labels

    func eceColor(_ ece: Double) -> Color { ece < 4 ? .green : (ece < 8 ? .blue : .orange) }

    /// "Jul 2026 – May 2026" style span, or nil if the payload omits the range.
    var dateRangeLabel: String? {
        guard let s = data?.dateRange?.start, let e = data?.dateRange?.end else { return nil }
        return "\(Self.monthYear(s))\u{2013}\(Self.monthYear(e))"
    }

    var updatedLabel: String {
        guard let g = data?.generatedAt, let date = Self.parseISO(g) else { return "hourly" }
        let f = DateFormatter(); f.dateFormat = "MMM d"
        return f.string(from: date)
    }

    // MARK: - Category / source normalization (mirrors the web maps)

    private static func normalizedCategory(_ category: String) -> String {
        if let mapped = sportKeyMap[category] { return mapped }
        let base = category.split(separator: "_").first.map(String.init) ?? category
        if base == "americanfootball" { return "football" }
        if base == "icehockey" { return "hockey" }
        return categoryDisplayNames[base] == nil ? category : base
    }

    static func categoryDisplayName(_ category: String) -> String {
        categoryDisplayNames[category] ?? category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    static func sourceDisplayName(_ source: String) -> String {
        sourceDisplayNames[source] ?? source.replacingOccurrences(of: "_", with: " ").capitalized
    }

    /// Display label for a raw (un-normalized) small-sample category token.
    static func nicheDisplayName(_ raw: String) -> String {
        categoryDisplayNames[normalizedCategory(raw)] ?? raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func monthYear(_ iso: String) -> String {
        guard let date = parseISO(iso) else { return iso }
        let f = DateFormatter(); f.dateFormat = "MMM yyyy"
        return f.string(from: date)
    }

    private static func parseISO(_ iso: String) -> Date? {
        let withFrac = ISO8601DateFormatter()
        withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFrac.date(from: iso) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: iso)
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

// MARK: - Presentation rows

struct CalSourceRow: Identifiable {
    let id = UUID()
    let source: String
    let name: String
    let n: Int
    let ece: Double
    let mce: Double
    let brier: Double
    let bucketsInBand: Int
    let totalBuckets: Int
}

struct CalCategoryRow: Identifiable {
    let id = UUID()
    let category: String
    let name: String
    let n: Int
    let ece: Double
    let mce: Double
    let brier: Double
}
