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

    /// L2-231 Item 1: a refresh that failed while a good payload is already on
    /// screen. The numbers stay — throwing away a readable curve because a later
    /// poll timed out is a worse answer than keeping it — but they stop being
    /// presented as current. `error` is reserved for having NOTHING to show.
    @Published private(set) var refreshFailed = false

    /// L2-74 §C default: the cohort is `price_moved != false` — outcomes whose
    /// price moved, PLUS the sportsbook lines where that test does not apply. The
    /// toggle layers the never-moved outcomes back in; it never hides, both counts
    /// are always visible. View-bound, so it stays mutable.
    ///
    /// The name is historical (L2-237 renamed the copy, not the property). It has
    /// never meant "thin" in the liquidity sense: zero-bid, zero-volume outcomes
    /// are excluded upstream, so nothing this flag adds is untraded — those rows
    /// traded and never moved off their opening line.
    @Published var includeThin = LaunchRig.startsIncludingUntraded()

    private static let nf: NumberFormatter = { let f = NumberFormatter(); f.numberStyle = .decimal; return f }()

    private var buckets: [CalibrationBucket] { data?.buckets ?? [] }

    // MARK: - Init

    /// How the model reaches the network. Injectable so the load STATES —
    /// transient refresh failure, cancellation, recovery — can be driven
    /// deterministically; `APIClient.shared` is a singleton and a live fetch
    /// cannot be asked to fail on demand.
    typealias Fetcher = () async throws -> CalibrationData

    private let fetcher: Fetcher

    init(fetcher: @escaping Fetcher = { try await APIClient.shared.fetchCalibration() }) {
        self.fetcher = fetcher
    }

    /// Preloaded-payload initializer.
    ///
    /// The production path is `load()`. This exists so the surface's payload
    /// STATES — dated last-good, version mismatch, empty, parked category — can
    /// be exercised directly. Those are states the server produces and a
    /// happy-path network stub never reaches, and they are precisely where
    /// native was silently diverging from web (L2-231 Item 0).
    init(preloaded: CalibrationData, fetcher: @escaping Fetcher = { try await APIClient.shared.fetchCalibration() }) {
        self.fetcher = fetcher
        self.data = preloaded
        self.loading = false
    }

    // MARK: - Loading

    /// Fetch, and be honest about which of the four outcomes happened.
    ///
    /// L2-231 Item 1 rewrote this. The previous three lines had three distinct
    /// ways to misreport:
    ///
    ///   1. `loading = true` unconditionally, so an explicit Retry on a screen
    ///      that already had numbers replaced them with a spinner.
    ///   2. Any thrown error became a full-screen error state, discarding a
    ///      perfectly readable curve because one later poll failed.
    ///   3. A CANCELLED request — the user leaving the tab mid-fetch, which
    ///      SwiftUI does routinely by cancelling the `.task` — took path 2 and
    ///      showed "cancelled" as though the server had broken.
    func load() async {
        let hadData = data != nil
        if hadData { refreshFailed = false } else { loading = true }
        error = nil
        do {
            let fresh = try await fetcher()
            data = fresh
            refreshFailed = false
        } catch {
            // A cancellation is not a failure and must never be reported as one.
            // Nothing changes: whatever was on screen stays exactly as it was.
            if !Self.isCancellation(error) {
                if hadData { refreshFailed = true } else { self.error = error.localizedDescription }
            }
        }
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

    /// Both shapes a cancelled `URLSession` request arrives in.
    nonisolated static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let urlError = error as? URLError, urlError.code == .cancelled { return true }
        return false
    }

    // MARK: - Availability (L2-231 Item 1)

    /// Whether there is a curve to draw at all.
    ///
    /// A payload that decoded but carries no buckets is NOT a 0.0pp result. Every
    /// metric on this screen divides by a bucket count, so an empty payload
    /// renders "0.0pp — Excellent", which is a confident claim manufactured out
    /// of no data. It has to be an honest unavailable state instead.
    var hasRenderableCurve: Bool { data != nil && !buckets.isEmpty }

    /// Set whenever the surface has settled with no curve to draw, and no other
    /// state already explains why.
    ///
    /// Covers three distinct endings that all used to fall through to the loaded
    /// layout and render "0.0pp \u{2014} Excellent" over nothing:
    ///   - a payload that decoded but carries an EMPTY `buckets` array;
    ///   - a payload whose `buckets` key was missing or unreadable;
    ///   - a load that ended without data and without an error, which is what a
    ///     CANCELLED first fetch leaves behind (the user opening the tab and
    ///     immediately leaving cancels the `.task`).
    ///
    /// Deliberately nil while `loading`, while `error` is set, and when the
    /// payload is version-incompatible — each of those has its own, more specific
    /// state, and stacking a second explanation on top would bury it.
    var unavailableMessage: String? {
        guard !loading, error == nil, !isIncompatible, !hasRenderableCurve else { return nil }
        guard let data else {
            return "We couldn't load the calibration numbers just now. Please try again."
        }
        return data.bucketsPresent
            ? "The calibration data came back empty this time. Nothing is wrong with "
                + "your app \u{2014} there is just nothing to plot yet. Please check back shortly."
            : "We couldn't read the calibration numbers the server sent. Rather than "
                + "show you something we can't stand behind, we're not showing anything. "
                + "Please check back shortly."
    }

    /// Buckets the server sent that this build could not read (L2-231 Item 1).
    var droppedBuckets: Int { data?.droppedBuckets ?? 0 }

    /// Shown whenever the curve is built from less than the payload offered. A
    /// silently-thinned curve reads exactly like a complete one.
    var partialDataNote: String? {
        let dropped = droppedBuckets
        guard dropped > 0 else { return nil }
        let total = dropped + buckets.count
        return "\(Self.fmt(dropped)) of \(Self.fmt(total)) data groups couldn't be read and "
            + "are not included below."
    }

    /// Shown when the last refresh failed but earlier numbers are still on screen.
    /// Names when they were built so they are never mistaken for current ones.
    var refreshFailureNote: String? {
        guard refreshFailed, data != nil else { return nil }
        let built = data?.generatedAt.flatMap(Self.parseISO)
        let whenText = built.map { date -> String in
            let f = DateFormatter(); f.dateFormat = "MMM d, h:mm a"
            return f.string(from: date)
        }
        return whenText.map { "Couldn't refresh just now \u{2014} still showing the numbers built \($0)." }
            ?? "Couldn't refresh just now \u{2014} these are the numbers from the last successful load."
    }

    // MARK: - Formatting helpers

    private static func fmt(_ n: Int) -> String { nf.string(from: NSNumber(value: n)) ?? "\(n)" }

    /// An em-dash for BOTH "no payload" and "the payload did not carry a readable
    /// count". A field the server omitted is unknown, and printing `0` for it is
    /// a number the reader cannot tell from a measured one (L2-231 Item 1).
    var formattedTotalOutcomes: String { data?.totalOutcomes.map(Self.fmt) ?? "\u{2014}" }
    var formattedMarkets: String { data?.totalMarkets.map(Self.fmt) ?? "\u{2014}" }
    var formattedCohortOutcomes: String { data == nil ? "\u{2014}" : Self.fmt(cohortN) }

    /// The population the hero claims to have analyzed, as the whole clause —
    /// the native equivalent of web's `describeCohort().heroClause`.
    ///
    /// Native used to lead with `total_outcomes` — the FULL total, a different
    /// number from the cohort the page below it measures, presented as the same
    /// claim (L2-231 Item 0). It now names the same population web does, in the
    /// same words, and says which outcomes are missing from it rather than
    /// labelling the remainder with a property nobody measured.
    ///
    /// **#7496 — two words, because `fullN` is not the total and one cut is not
    /// every cut.** `total_outcomes` is a POST-exclusion population, and this
    /// page says so about itself nine screens down: *"that published total is
    /// lower than the raw resolved-outcome count because we exclude markets that
    /// can't form an honest prediction"*. The eight folded rules alone set aside
    /// 147,721 outcomes. So the old sentence over-claimed twice: `(N in total)`
    /// called a filtered population everything, and *"every outcome except the
    /// never-moved ones"* named one cut as the only cut. Scoping the universe to
    /// what we MEASURED fixes both at once — the never-moved rows really are the
    /// only thing taken out of the measured set, which is the claim this sentence
    /// can support.
    ///
    /// #1865 (a)/(c) — **the phone now says "untraded", as web does.** This block
    /// used to explain why native deliberately did not: L2-236 ruled the word out
    /// because those rows are `price_moved == false` — they traded, they just
    /// never moved. That objection is factually right and was OVERRULED by Alex
    /// (2026-08-13 eyeball session, UX-P075 item (a)): *rename the excluded cohort
    /// "untraded" everywhere.* Web took the rename in August (`lib/calibrationCohort.ts`
    /// records the reversal under ruling 055); native kept the overruled wording,
    /// so the one page whose job is credibility named its two cohorts two ways on
    /// two surfaces. What survives of L2-236 is the narrower ban web kept: no
    /// string may assert ACTIVITY ("well-traded", "actively traded", a trade
    /// count). `testNoCohortStringMakesALiquidityClaim` holds that line now.
    var heroPopulationText: String {
        guard data != nil else { return "\u{2014} resolved predictions" }
        if includeThin || unchangedN == 0 { return "\(formattedCohortOutcomes) resolved predictions" }
        return "\(formattedCohortOutcomes) resolved predictions \u{2014} every outcome we measured "
            + "except the \(Self.fmt(unchangedN)) untraded ones, whose price never moved off its "
            + "opening line (\(Self.fmt(fullN)) measured in all)"
    }

    // MARK: - Cohort banner (#1865 — web's `describeCohort`, string for string)

    /// The cohort's name. UX-P080 item 3 (Alex, round 2): the default cohort is
    /// THE TRADED OUTCOMES — sportsbook lines are traded by construction, a
    /// sportsbook moves its line with money — so they are part of it, not an
    /// appendix to it. The unit is the OUTCOME (#7750): a market resolves into
    /// many outcomes, so "markets (N)" would name a smaller quantity.
    var cohortHeadline: String {
        includeThin
            ? "Showing all outcomes (\(formattedCohortOutcomes))"
            : "Showing traded outcomes (\(formattedCohortOutcomes))"
    }

    /// The ADJECTIVE slot (#7750): its consumers supply their own noun over their
    /// own number ("Traded (413,406 outcomes)"), so "All markets" would print a
    /// noun and its counter-noun over one number.
    var cohortShortLabel: String { includeThin ? "All" : "Traded" }

    /// The toggle button's label: the cohort it switches TO, and what that costs.
    /// With nothing untraded there is nothing to include or exclude.
    var cohortToggleLabel: String {
        guard unchangedN > 0 else { return "Show every outcome" }
        return includeThin ? "Exclude untraded" : "Include untraded (+\(Self.fmt(unchangedN)))"
    }

    /// What VoiceOver reads for that button. The visible label is a two-word verb
    /// phrase sized for a capsule; read on its own it never says what it acts on.
    var cohortToggleAccessibilityLabel: String {
        (includeThin ? "Exclude" : "Include")
            + " the \(Self.fmt(unchangedN)) untraded outcomes, whose price never moved off its opening line"
    }

    /// The sentence under the cohort name. Rendered straight after the headline,
    /// so it never restates the count the headline just printed (#7330): "Of
    /// those" names the sportsbook rows as a SUBSET of the traded cohort, not a
    /// third thing beside it. An empty excluded side excludes nothing and gets no
    /// clause — "Excluded: 0 untraded outcomes" states a non-fact.
    var cohortDetail: String {
        let na = notApplicableN
        if includeThin {
            return na > 0
                ? "\(Self.fmt(movedN + na)) traded (including \(Self.fmt(na)) sportsbook lines) "
                    + "\u{00B7} \(Self.fmt(unchangedN)) untraded."
                : "\(Self.fmt(movedN)) traded \u{00B7} \(Self.fmt(unchangedN)) untraded."
        }
        let excluded = unchangedN > 0
            ? " Excluded: \(Self.fmt(unchangedN)) untraded outcomes, whose price never moved off its opening line."
            : ""
        return na > 0
            ? "Of those, \(Self.fmt(na)) are sportsbook lines.\(excluded)"
            : "Every traded outcome.\(excluded)"
    }

    // MARK: - Sample gate

    /// #997: the minimum-sample bar comes from the API (Redis-tunable) so web and
    /// native gate on the same threshold. Fall back to 1000 if a lean/older
    /// payload omits it — never regress to a noisy floor.
    var minCategoryOutcomes: Int { data?.minCategoryOutcomes ?? 1000 }

    // MARK: - Cohort metrics (ECE-first)

    /// Aggregated curve for the active cohort (`price_moved != false` by default).
    var cohortBuckets: [CalibrationMath.AggBucket] {
        let thin = includeThin
        return CalibrationMath.aggregate(buckets) { thin || $0.priceMoved != false }
    }

    /// Headline metric: n-weighted error (pp). This is what the web page leads with.
    var cohortECE: Double { CalibrationMath.ece(cohortBuckets) }
    /// Demoted secondary: the equal-weighted mean error across the ten buckets
    /// (pp). Drawn under the `Bucket` header; the key stays `mce` for web
    /// parity (#7174).
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

    /// #8485 — the published bootstrap interval, only when the figure beside it
    /// was measured over the interval's own population. Web's
    /// `mceIntervalForCohort` (#7374): `mce_ci_*` is bootstrapped ONCE over every
    /// bucket with no `price_moved` filter, so on the traded view it is the
    /// interval of outcomes the screen has just excluded. Keyed on the
    /// POPULATION, not the toggle: a payload with no untraded outcomes has one
    /// population in both states. `nil` prints nothing, and says nothing.
    static func intervalForCohort(
        lower: Double?, upper: Double?, cohortN: Int, fullN: Int
    ) -> (lower: Double, upper: Double)? {
        guard let lower, let upper, lower.isFinite, upper.isFinite,
              lower >= 0, lower <= upper, fullN > 0, cohortN == fullN
        else { return nil }
        return (lower, upper)
    }

    var cohortInterval: (lower: Double, upper: Double)? {
        Self.intervalForCohort(
            lower: data?.mceCiLower, upper: data?.mceCiUpper, cohortN: cohortN, fullN: fullN)
    }
    /// The default cohort's size, independent of the toggle. Historical name;
    /// the predicate is `price_moved != false`, not a liquidity measure (L2-237).
    var wellTradedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved != false } }
    /// What the toggle adds: the never-moved outcomes. Historical name (L2-237).
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

    /// Normalized, sample-gated categories. The publish bar is the ONLY filter,
    /// because it is the only one the screen tells the reader about (#7533).
    ///
    /// There used to be a `.prefix(15)` on the end of this chain, and
    /// `topCategoryRows` took a further 10 by ECE on top of it. Neither was
    /// stated anywhere a reader could see, and between them they contradicted
    /// the caption directly above the table:
    ///
    ///   * the caption says categories are held out for being **below the bar**
    ///     — measured on `/api/calibration` 2026-09-20, 21 categories cleared
    ///     the 1,000-outcome bar and **10** were drawn;
    ///   * the 11 in the gap reached neither list. The niche card below is the
    ///     backend's `small_sample_categories` — the population **under** the
    ///     bar — so a category that cleared the bar and lost the slice appeared
    ///     nowhere, while both lists read as exhaustive;
    ///   * and the two slices sorted on **different orderings**, so the outcomes
    ///     slice could cut a row that belonged in the ECE ranking the caption
    ///     promises. It did: with the slice, rank 7 of the drawn rows was
    ///     Politics (8.3K, ECE 2.69); without it, rank 7 is `other` (1,356,
    ///     ECE 2.50) — better calibrated, and dropped for being smaller.
    ///
    /// Web deleted the same slice in #7302 and carries no second cap, so this is
    /// one family rendering one way on both surfaces rather than a native choice.
    ///
    /// The eligibility basis stays ALL-COHORT deliberately — do not filter on
    /// the cohort here. #7195 settled that the bar is applied by the backend on
    /// the all-cohort count (geopolitics publishes at 1,749 all-cohort against a
    /// 732 traded count), so cohort-scoping the bar would park a category under
    /// a 1,000 bar beside a table publishing one at 732 in the same view. The
    /// COUNTS are cohort-scoped downstream in `categoryRows`; that is a
    /// different question, and `CalibrationPopulation` is the caption that
    /// reconciles the two.
    var categories: [String] {
        let bks = buckets
        let minN = minCategoryOutcomes
        var catMap: [String: Int] = [:]
        for b in bks { catMap[Self.normalizedCategory(b.category), default: 0] += b.n }
        return catMap
            .filter { $0.value >= minN }
            .sorted { $0.value > $1.value }
            .map { $0.key }
    }

    /// #3650: metrics are withheld (`nil`) when the cohort holds no outcomes for
    /// the source, and unmeasured rows are ordered out of the ranking rather
    /// than into first place. `datagolf` publishes 36 outcomes, all
    /// `price_moved: false`, so the default cohort empties it and every metric
    /// it reported was an empty reduction's `0`. See `CalibrationRowOrdering`.
    ///
    /// #8485 — one row per PROVIDER, the way web's Source Comparison has drawn
    /// it since queue 316 (`frontend/lib/calibrationProviders.ts`). This used to
    /// map over raw source keys, so the four Odds API keys were four rows, and
    /// "Spreads (Odds API)" — 15.1K outcomes, 0.3pp ECE over a 14.9pp per-bucket
    /// error — ranked FIRST, above Kalshi, on the same payload where the website
    /// printed one Sportsbooks row at 1.1pp. The provider row pools its members'
    /// buckets and runs the same metric every other row runs, so it is a
    /// measurement of the provider's outcomes, never an average of four summaries.
    var sourceRows: [CalSourceRow] {
        let bks = buckets
        let thin = includeThin
        let served = data?.sourceLabels
        let rows = Self.providerGroups(sources).map { group -> CalSourceRow in
            let members = Set(group.members)
            let f: (CalibrationBucket) -> Bool = { members.contains($0.source) && (thin || $0.priceMoved != false) }
            let agg = CalibrationMath.aggregate(bks, filter: f)
            let band = agg.filter { abs($0.error) <= 5 }.count
            let n = CalibrationMath.totalN(bks, filter: f)
            // #6211: a population that all won (or all lost) is withheld the way
            // an empty one is. Web's Source Comparison has done this since
            // bae9f393b7. See `CalibrationRowOrdering.censoringVerdict`.
            let w = CalibrationRowOrdering.pooledWinners(bks.filter(f))
            let name = Self.providerDisplayName(group.provider, served: served)
            return CalSourceRow(
                source: group.provider, name: name,
                memberNames: group.members.count > 1
                    ? group.members.map {
                        Self.withoutGroupQualifier(Self.sourceDisplayName($0, served: served), groupName: name)
                    }
                    : [],
                n: n,
                winners: w,
                ece: CalibrationRowOrdering.metric(CalibrationMath.ece(agg), outcomes: n, winners: w),
                mce: CalibrationRowOrdering.metric(CalibrationMath.mce(agg), outcomes: n, winners: w),
                brier: CalibrationRowOrdering.metric(CalibrationMath.brier(bks, filter: f), outcomes: n, winners: w),
                bucketsInBand: band, totalBuckets: agg.count
            )
        }
        return CalibrationRowOrdering.orderedByECE(rows)
    }

    // MARK: - Providers (#8485, web's `providerOf` / `groupSourcesByProvider`)

    /// The provider a source key belongs to. Total: an unknown key is its own
    /// provider, so Kalshi and Polymarket are one-member providers, not
    /// exemptions — the same rule applied to every key.
    static func providerOf(_ source: String) -> String {
        if source == "odds_api" || source.hasPrefix("odds_api_") { return "odds_api_family" }
        return source
    }

    /// Source keys grouped by provider, providers and members both in the order
    /// the keys arrive (`sources` is largest-first).
    static func providerGroups(_ sources: [String]) -> [(provider: String, members: [String])] {
        var order: [String] = []
        var members: [String: [String]] = [:]
        for src in sources {
            let provider = providerOf(src)
            if members[provider] == nil { order.append(provider) }
            members[provider, default: []].append(src)
        }
        return order.map { ($0, members[$0] ?? []) }
    }

    /// A provider's row name. One-member providers are named as their source.
    static func providerDisplayName(_ provider: String,
                                    served: [String: CalibrationSourceLabel]? = nil) -> String {
        provider == "odds_api_family" ? "Sportsbooks (Odds API)" : sourceDisplayName(provider, served: served)
    }

    /// "Spreads (Odds API)" under "Sportsbooks (Odds API)" reads "Spreads" —
    /// web's `withoutGroupQualifier`. Untouched when the group has no
    /// parenthesised qualifier, the member does not carry it, or stripping would
    /// leave nothing.
    static func withoutGroupQualifier(_ memberName: String, groupName: String) -> String {
        guard let open = groupName.lastIndex(of: "("), groupName.hasSuffix(")") else { return memberName }
        let suffix = " " + groupName[open...]
        guard memberName.hasSuffix(suffix) else { return memberName }
        let stripped = memberName.dropLast(suffix.count).trimmingCharacters(in: .whitespaces)
        return stripped.isEmpty ? memberName : stripped
    }

    /// #3650: the same guard as `sourceRows`, and it is load-bearing rather than
    /// decorative. `categories` gates on outcomes counted across ALL buckets,
    /// while the row's own `n` is counted over the ACTIVE COHORT — so a category
    /// can clear `minCategoryOutcomes` on its total and still be empty here,
    /// exactly as `datagolf` does among the sources. Measured 2026-09-06: no
    /// category is currently in that state, which is a fact about today's data
    /// and not a property of the code.
    var categoryRows: [CalCategoryRow] {
        let bks = buckets
        let thin = includeThin
        let rows = categories.map { cat -> CalCategoryRow in
            let f: (CalibrationBucket) -> Bool = { Self.normalizedCategory($0.category) == cat && (thin || $0.priceMoved != false) }
            let agg = CalibrationMath.aggregate(bks, filter: f)
            let n = CalibrationMath.totalN(bks, filter: f)
            return CalCategoryRow(
                category: cat, name: Self.categoryDisplayName(cat), n: n,
                ece: CalibrationRowOrdering.metric(CalibrationMath.ece(agg), outcomes: n),
                mce: CalibrationRowOrdering.metric(CalibrationMath.mce(agg), outcomes: n),
                brier: CalibrationRowOrdering.metric(CalibrationMath.brier(bks, filter: f), outcomes: n)
            )
        }
        return CalibrationRowOrdering.orderedByECE(rows)
    }

    // #7533 — `topCategoryRows` (`categoryRows.prefix(10)`) is deliberately gone
    // rather than widened. The table draws `categoryRows`, so the array the
    // caption describes and the array the `ForEach` iterates are the same one by
    // construction and cannot drift apart again. A named "top N" property is how
    // the second cap survived #7302's sweep of the first.

    /// Best/worst consider MEASURED rows only. A "Best Calibrated" card naming a
    /// category with no outcomes would be the headline version of #3650.
    ///
    /// #7533: these now range over every category that clears the bar, not the
    /// ten that survived two slices. "Best calibrated" naming the best of an
    /// arbitrary subset was the headline wearing the table's defect.
    private var measuredCategoryRows: [CalCategoryRow] { categoryRows.filter { $0.ece != nil } }
    var bestCategoryRow: CalCategoryRow? { measuredCategoryRows.first }
    var worstCategoryRow: CalCategoryRow? { measuredCategoryRows.last }

    // MARK: - Trading-activity split (always the full moved/unchanged cohorts)

    var movedBuckets: [CalibrationMath.AggBucket] { CalibrationMath.aggregate(buckets) { $0.priceMoved == true } }
    var unchangedBuckets: [CalibrationMath.AggBucket] { CalibrationMath.aggregate(buckets) { $0.priceMoved == false } }
    var movedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved == true } }
    var unchangedN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved == false } }
    var movedECE: Double { CalibrationMath.ece(movedBuckets) }
    var unchangedECE: Double { CalibrationMath.ece(unchangedBuckets) }

    /// The THIRD activity state, which this surface had no name for.
    ///
    /// `price_moved` is a tri-state, not a boolean: `true` (the price moved),
    /// `false` (it never did), and `null` — sportsbook moneylines, spreads and
    /// totals, where "did trading move the price" is not a question the source
    /// can answer, so it is NOT APPLICABLE rather than false.
    ///
    /// Native modelled it as two states. `movedN + unchangedN` therefore fell
    /// short of the page's own population — on the 2026-08-02 payload, 349,310 +
    /// 263,022 = 612,332 against a stated 652,407 — with the 40,075 missing rows
    /// named nowhere. The partition is now complete and asserted:
    /// `movedN + unchangedN + notApplicableN == fullN`.
    var notApplicableN: Int { CalibrationMath.totalN(buckets) { $0.priceMoved == nil } }

    /// Reconciles the two trading-activity cards with the page's population. Nil
    /// when there are no not-applicable rows, so the note never appears as
    /// boilerplate on a payload it does not describe.
    ///
    /// #1865 — web's `describeActivityScope` caption (#7519). This note used to
    /// say sportsbook lines "sit in neither cohort", which was true of the old
    /// framing and contradicts the new one: everywhere else the page counts them
    /// as TRADED (UX-P080 item 3). It stays true of THESE TWO CARDS, which are the
    /// price-moved test, so the note says that — scoped to the cards — and keeps
    /// the sum, so the Traded card's count is never read as the page's traded total.
    var activityPartitionNote: String? {
        let na = notApplicableN
        guard na > 0 else { return nil }
        return "Both cards are the price-moved test, so the \(Self.fmt(na)) sportsbook lines \u{2014} "
            + "traded, but never put to that test \u{2014} are in neither: \(Self.fmt(movedN)) + "
            + "\(Self.fmt(unchangedN)) + \(Self.fmt(na)) = \(Self.fmt(fullN)) resolved outcomes."
    }

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
        let schedule = scheduleClause.map { " " + $0 } ?? ""
        return "These numbers were built \(whenText)\(age) and are not being "
            + "refreshed right now.\(schedule)"
    }

    /// The closing sentence about the hourly schedule, or `nil` for "say nothing".
    ///
    /// #2649. This used to be the literal tail of `staleBannerDetail`: "The curve
    /// rebuilds hourly.", unconditionally. On 2026-09-02 the payload carrying it
    /// also carried `producer: { stalled: true, beats_missed: 51 }` — so both
    /// surfaces spent 51 hours telling readers to come back in an hour, for a
    /// stall that could not self-resolve (the publish gate was refusing every
    /// rebuild and binning it).
    ///
    /// Kept as a sentence rather than deleted, because when the beat IS landing
    /// the cadence is useful and checkable. What changed is that it must now be
    /// earned. Mirrors `frontend/lib/calibrationStaleness.ts`
    /// `stalenessScheduleClause` state for state — the cross-client contract
    /// means a web-only fix would leave this surface saying the false thing.
    ///
    /// Three readings, and absence is deliberately NOT the reassuring one
    /// (gotcha #53): a payload with no `producer` block is not evidence of a
    /// healthy beat, so it gets silence rather than the promise.
    var scheduleClause: String? {
        guard let producer = data?.producer else { return nil }
        if producer.beatIsLanding { return "The curve rebuilds hourly." }
        guard producer.stalled == true else { return nil }
        guard let missed = producer.beatsMissed, missed > 0 else {
            return "Hourly rebuilds are not currently succeeding."
        }
        let noun = missed == 1 ? "hourly rebuild has" : "hourly rebuilds have"
        return "\(missed) \(noun) come and gone without one succeeding."
    }

    /// The population contracts THIS BUILD's labels honestly describe.
    ///
    /// This is a CONTRACT check, not a freshness check. Native cannot recompute
    /// the population, so if the payload announces one this build was not written
    /// against, the honest answer is to refuse rather than to render current-looking
    /// labels over numbers built under different rules (C111 P2 / Q297 §3).
    ///
    /// L2-232 — WHY THIS IS A SET AND NOT ONE STRING.
    ///
    /// L2-231 shipped `expectedPopulationVersion = "q299"`, compared for equality.
    /// Hours later `dc79c9b4` rolled the SERVER back to q267, because bumping the
    /// backend constant had invalidated the only good cached artifact and taken
    /// the public web page dark for ~90 minutes. The rollback was correct — and
    /// it left this app refusing a perfectly valid payload, because its own
    /// constant no longer matched. A client-side equality check turned the
    /// server's recovery into a native outage.
    ///
    /// So the set holds every population this build can label, which makes a
    /// server-side roll-forward OR roll-back between listed versions a non-event
    /// here. `frontend/e2e/contract/populationVersion.contract.test.js` fails CI
    /// if the backend's published version is missing from this list (and from
    /// web's), so the two can no longer drift apart unobserved.
    ///
    /// Keep this in step with `COMPATIBLE_POPULATION_VERSIONS` in
    /// `frontend/lib/calibrationContract.ts` — same claim, same rollout order:
    /// widen the clients FIRST, bump the backend SECOND.
    // INT-065 2026-08-13: CAL-P045 (#1530) bumped the backend q267 -> q1530. Both are listed
    // so this build accepts either for the whole rollout window — and a shipped iOS build
    // cannot be rolled back, which is why native must never be the narrower of the two.
    //
    // CAL-P070 2026-08-18: "q268" added (#1955/#1680). q268 is a LABEL-ONLY bump —
    // same CTEs, same exclusions, same metrics as q267 — so this build's labels
    // describe it by construction. "q267" stays because the backend deliberately
    // keeps serving the last q267 artifact, dated and degraded, until the first
    // q268 build publishes; a narrower set here would refuse precisely the
    // payload that keeps the surface lit.
    //
    // WHAT THIS COMMIT CANNOT FIX: builds ALREADY on devices ship the old set and
    // will read q268 as `.incompatible` until their owners update. That is a cost
    // of the bump itself, not of this list, and it is the reason the rollout order
    // is clients-first whenever there is a choice.
    // CAL-P211 2026-09-01: "q269" added (#1978), and it is NOT a label-only bump
    // like q268 was. The ruled freeze-lift batch excludes 201,508 outcomes, so a
    // q269 curve genuinely counts different rows. This build's labels survive it
    // because they describe how rows are plotted, not which rows qualify; the
    // only cell that changes identity is crypto, and it LEAVES the board (parked
    // below the 1,000-row bar) rather than being relabelled underneath a caption.
    //
    // The warning immediately above applies with full force here and is worse for
    // native than for web: builds ALREADY on devices ship the old set and will
    // read q269 as `.incompatible` until their owners update, and a shipped iOS
    // build cannot be rolled back. That cost is unavoidable in either deploy
    // order — it is a cost of the bump, not of the ordering — and it is called
    // out in `alex-inbox/calibration-021` so it is decided rather than
    // discovered.
    // CAL-P1137 2026-09-12: "q270" added (#5401, #5305) — the one recount. Like
    // q269 and unlike q268 it MOVES the methodology: the Kalshi writer bar stops
    // grading openings no order book stood behind, and a threshold ladder is
    // collapsed to one forecast instead of forty. This build's labels survive
    // both for the q269 reason — they describe how rows are plotted, not which
    // rows qualify — and no cell changes identity under an unchanged caption.
    //
    // The web half of the raw -> published reconciliation gained a new bullet
    // for the writer bar in the same commit. Native does not render that
    // exclusions list, so there is no native copy to teach; the correction is
    // carried in the corrections log this surface already reads.
    //
    // The on-device warning above applies unchanged: builds already shipped
    // carry the old set and read q270 as `.incompatible` until updated.
    //
    // CAL-P1138 2026-09-13: "q271" added (#997, D112) — the recount's last
    // method item. It is the first bump in this set that WIDENS rather than
    // narrows: it admits the lone-claim settlement pair and removes nothing, so
    // unlike q269 and q270 it introduces no exclusion class at all. Native
    // renders no exclusions list and decodes no filter block, so — as with
    // q270 — the only thing this surface needs is the version token. No label
    // here names a population rule, and no cell changes identity.
    //
    // The on-device warning bites here too and is the reason this entry ships
    // with the backend rather than after it: a build already on a phone carries
    // the old set and will read q271 as `.incompatible` until it is updated.
    static let compatiblePopulationVersions: Set<String> = ["q267", "q268", "q269", "q270", "q271", "q1530"]

    var populationVersion: String? { data?.populationVersion }

    // MARK: - Cross-surface parity (CAL-P026, exam item 5)

    /// The figures web publishes as `data-*` attributes on `/calibration`, in one
    /// place, so the surface's accessibility hooks and the parity tests read the
    /// SAME values rather than each recomputing them.
    ///
    /// ## Why native needed this at all
    ///
    /// The exit exam asks for native and web "showing the same population
    /// version, the same generated-at, and the same headline figures". Web can
    /// answer that question mechanically: `app/calibration/page.tsx` publishes
    /// `data-population-version`, `data-cache-status`, `data-contract-state`,
    /// `data-generated-at`, `data-cohort-n`, `data-full-n` and the partition
    /// counts, and `calibrationAuditHooks.test.tsx` fails CI if one is dropped.
    /// Native published NOTHING — the whole surface carried zero
    /// `accessibilityIdentifier`s — so the only way to compare the two was for a
    /// person to squint at two screenshots.
    ///
    /// That is the failure this exam keeps rediscovering in other forms: a
    /// property that can only be checked by eye is checked once, on the day
    /// somebody cares, and then drifts silently. Web's own source says so, in the
    /// comment above its population-count hook — *"a native surface reading the
    /// other one diverges silently. Both are published here as data so the parity
    /// check reads numbers, not text."* The data half of that sentence was
    /// written for a consumer that did not exist yet. This is that consumer.
    ///
    /// ## What this is NOT
    ///
    /// It is not a second derivation. Every field below reads an existing
    /// published property or an existing `CalibrationMath` roll-up — the same
    /// ones the visible surface renders. Ruling 003 ("clients format, never
    /// adjudicate") forbids computing a calibration number twice in two
    /// languages, and CAL-P025 was caught by exactly that rule mid-build. If a
    /// figure is wrong here it is wrong on screen too, which is the point: the
    /// hooks must describe the surface, not shadow it.
    struct Parity: Equatable {
        var populationVersion: String
        var contractState: String
        var cacheStatus: String
        var generatedAt: String
        var cohortN: Int
        var fullN: Int
        var movedN: Int
        var unchangedN: Int
        var notApplicableN: Int
        var ece: Double
        var mce: Double
        var brier: Double
        var markets: Int

        /// The partition invariant web publishes as `data-partition-reconciles`.
        var reconciles: Bool { movedN + unchangedN + notApplicableN == fullN }
    }

    /// `contractState` mirrors web's `data-contract-state`: what THIS BUILD
    /// decided about the version the server sent, which is a different fact from
    /// the version itself. Web draws the same distinction for the same reason.
    var parity: Parity {
        let state: String
        switch populationVersionState {
        // CAL-P043 (#1643): these are WEB'S spellings, not native's own.
        //
        // Native published "matched"/"mismatched" while web published
        // "match"/"incompatible" for the same payload and the same field name —
        // a real cross-surface divergence that survived because the gate which
        // claimed to compare the two surfaces never read a web value (codex
        // C236). Web's vocabulary wins because it is the one that ships
        // publicly and the one the browser-audit rail grades on
        // (`e2e/specs/calibration.spec.ts` requires the rendered state to be
        // "match" or "unverified").
        //
        // Web has a fourth state, "malformed", for a `population_version` that
        // is present but not a string. It is unreachable here: the field
        // decodes as `String?`, so a non-string payload fails decoding long
        // before it reaches this switch. Absent by construction, not omitted.
        case .matched: state = "match"
        case .mismatched: state = "incompatible"
        case .unverified: state = "unverified"
        }
        return Parity(
            populationVersion: data?.populationVersion ?? "",
            contractState: state,
            cacheStatus: data?.cache?.status ?? "fresh",
            generatedAt: data?.cache?.generatedAt ?? data?.generatedAt ?? "",
            cohortN: cohortN,
            fullN: fullN,
            movedN: movedN,
            unchangedN: unchangedN,
            notApplicableN: notApplicableN,
            ece: cohortECE,
            mce: cohortMCE,
            brier: cohortBrier,
            markets: data?.totalMarkets ?? 0
        )
    }

    /// `nil`/blank payload version means an older/lean payload that predates the
    /// contract field — rendered, but never claimed as verified. Refusing those
    /// would hand any older cached copy the power to blank the screen.
    var populationVersionState: PopulationVersionState {
        guard let raw = data?.populationVersion else { return .unverified }
        let v = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if v.isEmpty { return .unverified }
        return Self.compatiblePopulationVersions.contains(v) ? .matched : .mismatched(v)
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

    /// L2-232: the same sentence web renders (`CONTRACT_REFUSAL_MESSAGE` in
    /// `frontend/lib/calibrationContract.ts`), for the same reasons.
    ///
    /// L2-231's wording printed both version strings — "This build reads
    /// calibration population q299, but the server published q267" — which is
    /// unexplained jargon to everyone outside this repo, and it blamed the
    /// server for a disagreement the client was equally party to. The versions
    /// are diagnostic, so they belong in the parity evidence, not in the
    /// reader's sentence.
    var incompatibleMessage: String? {
        guard case .mismatched = populationVersionState else { return nil }
        // The tail differs from web's by one clause, deliberately: web promises
        // the page "updates automatically" because SWR re-polls every 5 minutes,
        // and native has no such poll — its recovery is the Retry button beside
        // this text. Promising an automatic update here would be a lie about
        // this surface, which is the class of thing this whole queue is about.
        return "We're not showing calibration numbers right now — we can't confirm this "
            + "app's descriptions match the data the server sent, and labelling them "
            + "wrong would be worse than not showing them. Please check back shortly."
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

    // MARK: - Held out, under review (#8476)

    /// Rows held out of every curve pending review, in payload order (web does not
    /// sort them either). Empty when the payload holds nothing OR never carried the
    /// key. Both hide the card, exactly as web's `quarantine.length > 0` gate does.
    var quarantine: [CalibrationQuarantine] { data?.quarantine ?? [] }
    var quarantineTotal: Int { quarantine.reduce(0) { $0 + $1.outcomes } }

    /// The count in full ("2,069"), because web prints `toLocaleString()` and a
    /// reader comparing the two screens must read the same number. `compactCount`'s
    /// "2.1K" would not be the same number.
    func quarantineCount(_ n: Int) -> String { Self.fmt(n) }

    /// Web's caption for the card, word for word (`app/calibration/page.tsx`,
    /// CAL-P067 item 5). Pinned against web's sentence in
    /// `CalibrationQuarantineTests8476`, so a wording change on one surface fails
    /// until the other follows.
    var quarantineCaption: String {
        let total = quarantineTotal
        return "\(Self.fmt(total)) resolved \(total == 1 ? "outcome is" : "outcomes are") "
            + "excluded from every curve on this page while we check them. They are not "
            + "graded, not counted, and not deleted \u{2014} a held-out row is a stated "
            + "exclusion we can reverse, which is the difference between a quarantine and a "
            + "quietly shorter denominator."
    }

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

    /// #3650: a withheld metric has no quality colour. Painting an unmeasured
    /// row green is the same claim its fabricated `0.0` was making, in pixels.
    func eceColor(_ ece: Double?) -> Color {
        guard let ece else { return .secondary }
        return eceColor(ece)
    }

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

    /// Internal rather than private since #7532: the guard for that ship has to
    /// name the PARENT a parked key rolls up to in order to assert that the chip
    /// never prints the parent's label.
    static func normalizedCategory(_ category: String) -> String {
        if let mapped = sportKeyMap[category] { return mapped }
        let base = category.split(separator: "_").first.map(String.init) ?? category
        if base == "americanfootball" { return "football" }
        if base == "icehockey" { return "hockey" }
        return categoryDisplayNames[base] == nil ? category : base
    }

    /// #1938: the map first, then ACRONYM-AWARE casing — never `.capitalized`,
    /// which renders the raw key "mma" as "Mma" (Alex, bug report 145). Any key
    /// the map does not carry is exactly the case that needs the safe formatter.
    ///
    /// #7722 — the safe formatter is not enough, and web already knew it. Its
    /// twin is `calibrationCategories.ts` `categoryLabel`, which reads
    /// `DISPLAY_NAMES[cat] || nicheCatLabel(cat)` — the LEAGUE-AWARE labeller,
    /// not a bare title-caser. This app carried the map and the bare title-caser,
    /// so the two surfaces answered differently for a compound league key the
    /// map does not carry: web printed **AFL** and **NRL** and the phone printed
    /// **"Aussierules Afl"** and **"Rugbyleague Nrl"**, a database identifier
    /// with its underscore swapped for a space, in the Category Breakdown.
    ///
    /// Routing this fallback to `nicheCategoryLabel` — which already exists, is
    /// already the Swift twin of `nicheCatLabel`, and already names a row by its
    /// OWN tokens — makes the two surfaces the same shape rather than adding two
    /// labels. That matters because the defect is scheduled, not accidental: the
    /// web file's own header records it, and both keys reached a reader on the
    /// day upstream growth carried them past the 1,000-outcome floor. Nothing on
    /// our side changed. The next key to cross it gets the league-aware name.
    ///
    /// Measured on the payload served 2026-09-21, this moves exactly two of the
    /// 21 published rows, both of them onto web's string.
    static func categoryDisplayName(_ category: String) -> String {
        categoryDisplayNames[category] ?? nicheCategoryLabel(category)
    }

    /// #3657 — the SOURCE path had the #1938 defect the CATEGORY path above was
    /// fixed for: `.capitalized` lowercases an interior capital, so the payload's
    /// `datagolf` rendered as "Datagolf". The two paths were disagreeing about the
    /// same problem, which is why this is a shared formatter and not a seventh map
    /// entry — `sourceDisplayNames` deliberately still has no `datagolf` key, so
    /// this fallback is what produces "DataGolf" and a test proves it.
    ///
    /// #3393 — between the two sits the server's own name (`served`, the
    /// payload's `source_labels`), in web's precedence: house style first, then
    /// the published label, then the formatter. The source key set is
    /// data-driven, so a key this build has never seen now arrives with the
    /// name web prints for it rather than one generated from its spelling. A
    /// blank served label is no name at all and falls through.
    static func sourceDisplayName(_ source: String,
                                  served: [String: CalibrationSourceLabel]? = nil) -> String {
        if let local = sourceDisplayNames[source] { return local }
        if let label = served?[source]?.label.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty {
            return label
        }
        return toTitleCaseAcronymSafe(source)
    }

    /// Display label for a raw (un-normalized) small-sample category token.
    ///
    /// #7532 — this used to read `categoryDisplayNames[normalizedCategory(raw)]`,
    /// which is the one lookup a parked category may not make: normalising is
    /// how a row finds its PARENT, and the parent is the row the Category
    /// Breakdown is publishing two inches above these chips. Measured on the
    /// 2026-09-20 payload, 67 of 109 chips came back wearing a published
    /// parent's name. The rule (L2-103 Item 3b, Alex D5) and its twin live in
    /// `nicheCategoryLabel`; this stays as the call site's name.
    static func nicheDisplayName(_ raw: String) -> String {
        nicheCategoryLabel(raw)
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
        // #7722 — web's `DISPLAY_NAMES` has carried this since UX-P075 item (e)
        // (Alex, 2026-08-13) and this map did not. Both surfaces already PRINT
        // "Table Tennis" — web from the entry, the phone from its fallback — so
        // this changes no pixel. It is here because the published set is where
        // the two maps must agree key-for-key (#3557): a curated label that
        // exists on one surface and is derived on the other is a drift waiting
        // for one of the two derivations to change.
        "table_tennis": "Table Tennis",
    ]

    /// **This map is what the phone prints, not the server's vocabulary.**
    ///
    /// `/api/calibration` publishes `source_labels` (owned by
    /// `backend/app/utils/calibration_source_labels.py`), and since #3393 this
    /// client reads it — but only for keys this map has no opinion about, which
    /// is web's precedence too: `makeSourceLabeller` consults its own house-style
    /// map FIRST and only falls through to the published label for keys it does
    /// not carry. So a rename applied to the backend alone changes nothing a
    /// reader sees on either client for a key listed here, and this entry has to
    /// move on its own account.
    ///
    /// `odds_api_bookmaker` is a payload key and stays as it is — it is a data
    /// contract, not prose. Its NAME may not carry the word: standing notice 33
    /// (Alex, 2026-09-08, on D92) bans "books"/"bookmaker(s)" from every string
    /// the app draws, and D91 makes "sportsbooks" the approved word.
    private static let sourceDisplayNames: [String: String] = [
        "kalshi": "Kalshi",
        "polymarket": "Polymarket",
        // #8485: "Moneylines", as web and `source_labels` name it — now drawn
        // as a member under "Sportsbooks (Odds API)", where a bare "Odds API"
        // beside "Spreads" and "Totals" named the supplier, not the shape.
        "odds_api": "Moneylines (Odds API)",
        "odds_api_spreads": "Spreads (Odds API)",
        "odds_api_totals": "Totals (Odds API)",
        "odds_api_bookmaker": "Per-sportsbook (Odds API)",
    ]
}

// MARK: - Presentation rows

/// #3650: the metrics are OPTIONAL, and that is the fix rather than a detail of
/// it. When the active cohort holds no outcomes for this row, every metric the
/// math returns is an empty reduction's `0` — indistinguishable, once it is a
/// plain `Double`, from a source measured and found perfect. Modelling the
/// absence as `nil` moves the check from a reviewer's attention to the
/// compiler's: a formatter cannot be handed one of these without saying what it
/// means to print when there is nothing to print.
struct CalSourceRow: Identifiable, CalibrationMetricRow {
    let id = UUID()
    /// The provider key (#8485): a source key, or `odds_api_family`.
    let source: String
    let name: String
    /// The pooled members' names, qualifier stripped; empty for a one-member provider.
    let memberNames: [String]
    let n: Int
    /// Winners pooled over the same cohort as `n` (#6211). The censored cell
    /// reads it to say which side the population fell on.
    let winners: Int
    /// `nil` when `n == 0`, or when the population is censored (#6211). See
    /// `CalibrationRowOrdering`.
    let ece: Double?
    let mce: Double?
    let brier: Double?
    let bucketsInBand: Int
    let totalBuckets: Int

    var state: CalRowState { CalibrationRowOrdering.state(outcomes: n, winners: winners) }
}

struct CalCategoryRow: Identifiable, CalibrationMetricRow {
    let id = UUID()
    let category: String
    let name: String
    let n: Int
    /// `nil` when `n == 0`. See `CalibrationRowOrdering`.
    let ece: Double?
    let mce: Double?
    let brier: Double?

    var state: CalRowState { CalibrationRowOrdering.state(outcomes: n) }
}
