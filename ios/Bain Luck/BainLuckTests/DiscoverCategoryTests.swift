import XCTest
@testable import Bain_Luck

/// #1883 — the Discover adjacency escape, and the classifier unification behind it.
///
/// Two things are pinned here:
///   1. `DiscoverCategory` is the ONE classifier. `DiscoverView.itemCategory` and
///      `DiscoverViewModel.category(for:)` used to be hand-maintained copies that
///      had drifted four ways (17% of live cards classified differently). They now
///      delegate, so agreement is STRUCTURAL — there is no second rule to assert
///      against. That is deliberately stronger than the "test the copies agree"
///      this issue originally asked for: an agreement test still permits two rules.
///   2. The non-sports drain breaks runs (`breakNonSportsRuns`). This is the
///      mandatory safety half of the concept fix — measured on 83 production
///      cards, the domain map ALONE takes the worst-case run from 6 to 8.
final class DiscoverCategoryTests: XCTestCase {

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func item(_ json: String) throws -> FeedItem {
        try Self.decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    private func concept(domain: String?, key: String = "event:x:1") throws -> FeedItem {
        let dom = domain.map { "\"\($0)\"" } ?? "null"
        return try item("""
        {"type":"concept","score":58,"data":{"key":"\(key)","name":"Card","domain":\(dom),
         "status":"upcoming","fight_count":12,"entry_count":0}}
        """)
    }

    private func futures(category: String?, id: Int = 1) throws -> FeedItem {
        let cat = category.map { "\"\($0)\"" } ?? "null"
        return try item("""
        {"type":"futures","score":90,"data":{"id":\(id),"name":"M\(id)?",
         "llm_sport_category":\(cat),"source":"kalshi","status":"open","outcome_count":1}}
        """)
    }

    private func event(sport: String?, id: Int = 1) throws -> FeedItem {
        let s = sport.map { "\"\($0)\"" } ?? "null"
        return try item("""
        {"type":"event","score":35,"data":{"id":\(id),"sport":\(s),"home_team":"H",
         "away_team":"A","commence_time":"2026-08-14T23:00:00+00:00","status":"live"}}
        """)
    }

    private func tournament(tour: String = "pga") throws -> FeedItem {
        try item("""
        {"type":"tournament","score":100,"data":{"key":"k","name":"N","tour":"\(tour)",
         "schedule_status":"upcoming"}}
        """)
    }

    /// NOTE the `bundle` key. `FeedItem.init` reads bundles from a **separate**
    /// `bundle` key, while production sends them under `data` — see
    /// `testProductionBundleWireShapeIsDroppedByTheDecoder` below, which pins that
    /// defect. This helper uses the shape the decoder actually accepts so the
    /// classifier tests exercise the classifier rather than the decode bug.
    private func bundle(childJSON: String, id: String = "b1") throws -> FeedItem {
        try item("""
        {"type":"bundle","score":89,"bundle":{"id":"\(id)","title":"T","kind":"theme",
         "items":[\(childJSON)]}}
        """)
    }

    private static let futuresChild = """
    {"type":"futures","score":90,"data":{"id":7,"name":"M?","llm_sport_category":"politics",
     "source":"kalshi","status":"open","outcome_count":1}}
    """

    // MARK: - 1. The concept domain map (the #1883 fix itself)

    func testConceptUFCMapsToMMA() throws {
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "ufc")), "mma")
    }

    func testConceptF1MapsToMotorsports() throws {
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "f1")), "motorsports")
    }

    func testConceptDomainIsCaseInsensitive() throws {
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "UFC")), "mma")
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "F1")), "motorsports")
    }

    func testUnmappedConceptDomainPassesThroughUnchanged() throws {
        // `cycling` has no entry ON PURPOSE: it is not in `sportsCategories`
        // either, and inventing a token would move cycling cards between
        // partitions on no evidence.
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "cycling")), "cycling")
    }

    func testConceptWithNoDomainIsOther() throws {
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: nil)), "other")
        XCTAssertEqual(DiscoverCategory.of(try concept(domain: "")), "other")
    }

    func testMappedConceptsNowLandInTheSportsPartition() throws {
        // THE BUG, stated as a test: these are what escaped the adjacency guard.
        XCTAssertTrue(DiscoverCategory.isSports(try concept(domain: "ufc")))
        XCTAssertTrue(DiscoverCategory.isSports(try concept(domain: "f1")))
    }

    func testRawDomainsAreStillNotSportsTokens() throws {
        // Pins WHY the map is needed — if someone "simplifies" it away, this reds.
        XCTAssertFalse(DiscoverCategory.sportsCategories.contains("ufc"))
        XCTAssertFalse(DiscoverCategory.sportsCategories.contains("f1"))
        XCTAssertTrue(DiscoverCategory.sportsCategories.contains("mma"))
        XCTAssertTrue(DiscoverCategory.sportsCategories.contains("motorsports"))
    }

    // MARK: - 2. The four measured divergences between the old copies

    func testTournamentClassification_isGolfByMeasurementNotByConstruction() throws {
        // `FeedTournamentData` carries NO sport field — only `tour`. Every
        // tournament card in the 83-card production sample was golf (`pga` /
        // `dp_world`), and the view's old fall-through default classified them
        // all "golf". Preserved deliberately so no live card changes partition.
        XCTAssertEqual(DiscoverCategory.of(try tournament(tour: "pga")), "golf")
        XCTAssertEqual(DiscoverCategory.of(try tournament(tour: "dp_world")), "golf")
        XCTAssertTrue(DiscoverCategory.isSports(try tournament()))
    }

    func testBundleTakesItsCategoryFromItsChild_notOther() throws {
        // The view model's old copy had NO bundle branch: every bundle was "other".
        // 6 of 83 live cards hit this.
        XCTAssertEqual(DiscoverCategory.of(try bundle(childJSON: Self.futuresChild)), "politics")
    }

    func testBundleChildResolverIsInjectable() throws {
        // The view passes an eligibility-gated resolver (C29 P2). Prove the seam
        // actually steers the verdict rather than being decorative.
        let b = try bundle(childJSON: Self.futuresChild)
        XCTAssertEqual(DiscoverCategory.of(b) { _ in nil }, "other")
    }

    func testFuturesCategoryIsLowercased() throws {
        // The view's old copy did NOT lowercase; the view model's did.
        XCTAssertEqual(DiscoverCategory.of(try futures(category: "Politics")), "politics")
        XCTAssertEqual(DiscoverCategory.of(try futures(category: nil)), "other")
    }

    func testEventTakesTheSportPrefix_andNilSportIsOtherNotSports() throws {
        XCTAssertEqual(DiscoverCategory.of(try event(sport: "americanfootball_nfl")), "americanfootball")
        // The view's old copy fell back to "sports", which is not in the sports
        // set — a sports-looking token that routed the card to nonSports anyway.
        XCTAssertEqual(DiscoverCategory.of(try event(sport: nil)), "other")
    }

    /// Pins a defect this cycle FOUND but did not fix, so the fix has a ready red.
    ///
    /// `FeedItem.init` reads bundles from a top-level `bundle` key. Production
    /// sends them as `{"type":"bundle","data":{…}}` — measured: **0 of 83** live
    /// feed items carried a `bundle` key, and all 6 bundle cards used `data`.
    /// `type == "bundle"` therefore falls into the `else` branch, decodes `data` as
    /// `FeedFuturesData`, throws on the string `id`, and `FeedResponse`'s tolerant
    /// skip loop drops the card silently — so every theme card ("2028 Election",
    /// "Fed & Rates", "Middle East") is invisible on iOS.
    ///
    /// Identical class to the L2-179 concept bug documented in `FeedItem.init`
    /// itself, which is why the comment there says the native marquee never
    /// appeared on device. When that is fixed, this test flips to a positive
    /// assertion and `testBundleTakesItsCategoryFromItsChild_notOther`'s helper
    /// should move back to the `data` shape.
    func testProductionBundleWireShapeIsDroppedByTheDecoder() throws {
        let productionShape = """
        {"type":"bundle","score":89,"reason":"2 related markets","headline":"2028 Election",
         "data":{"id":"theme:story:us_2028_election:108326-108445","title":"2028 Election",
         "kind":"theme","item_count":2,"items":[\(Self.futuresChild)]}}
        """
        XCTAssertThrowsError(try item(productionShape),
                             "documents the live decode drop — see the doc comment")
    }

    func testSportsCategorySetIsTheOneSharedCopy() throws {
        XCTAssertEqual(DiscoverCategory.sportsCategories.count, 14)
        XCTAssertTrue(DiscoverCategory.isSports(try event(sport: "basketball_nba")))
        XCTAssertFalse(DiscoverCategory.isSports(try futures(category: "politics")))
    }

    // MARK: - 3. The safety half — breaking runs in the non-sports drain

    private struct Stub: Equatable { let id: Int; let cat: String }
    private let sportsCats: Set<String> = ["basketball", "football", "baseball", "hockey", "soccer"]
    private func cat(_ s: Stub) -> String { s.cat }

    private func maxRun(_ xs: [Stub]) -> Int {
        var best = xs.isEmpty ? 0 : 1, cur = 1
        for (a, b) in zip(xs, xs.dropFirst()) {
            cur = a.cat == b.cat ? cur + 1 : 1
            best = max(best, cur)
        }
        return best
    }

    /// The measured production shape: a small sports partition that runs dry, then
    /// a long single-category non-sports tail (page `offset=30`, 2026-08-14).
    private func drainingFixture() -> [Stub] {
        var out = (0..<4).map { Stub(id: $0, cat: "basketball") }
        out += (0..<12).map { Stub(id: 100 + $0, cat: "politics") }
        out += (0..<3).map { Stub(id: 200 + $0, cat: "economics") }
        return out
    }

    func testNonSportsRunIsBrokenWhenEnabled() {
        let f = drainingFixture()
        let off = FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                            breakNonSportsRuns: false, category: cat)
        let on = FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                           breakNonSportsRuns: true, category: cat)
        XCTAssertGreaterThan(maxRun(off), maxRun(on),
                             "the non-sports guard must shorten the tail run it was added for")
    }

    func testDefaultIsBitForBitTheLegacyOrder() {
        // Monotone: the opt-in default cannot change any existing call's order.
        for n in [0, 1, 2, 3, 5, 50, 200] {
            let f = (0..<n).map { Stub(id: $0, cat: ["basketball", "politics", "baseball", "tech"][$0 % 4]) }
            XCTAssertEqual(
                FeedInterleave.byCategory(f, sportsCategories: sportsCats, category: cat),
                FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                          breakNonSportsRuns: false, category: cat),
                "explicit false must equal the defaulted call at n=\(n)")
        }
    }

    func testGuardIsInertWhenThereIsNothingToBreak() {
        // No two adjacent non-sports cards share a category → bit-for-bit identical.
        let f = [Stub(id: 1, cat: "politics"), Stub(id: 2, cat: "basketball"),
                 Stub(id: 3, cat: "tech"), Stub(id: 4, cat: "baseball"),
                 Stub(id: 5, cat: "economics")]
        XCTAssertEqual(
            FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                      breakNonSportsRuns: true, category: cat),
            FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                      breakNonSportsRuns: false, category: cat))
    }

    // gotcha #43 — a cap's guard tests must assert BOTH directions.
    func testSportsPartitionIsNotStarvedByTheNonSportsGuard() {
        let f = drainingFixture()
        let on = FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                           breakNonSportsRuns: true, category: cat)
        XCTAssertEqual(on.filter { sportsCats.contains($0.cat) }.count, 4,
                       "every sports card must still be present")
        XCTAssertEqual(Set(on.map(\.id)), Set(f.map(\.id)), "no card dropped or duplicated")
        XCTAssertEqual(on.count, f.count)
    }

    func testNoCardIsLostOrDuplicatedAtAnySize() {
        for n in [3, 17, 50, 200, 500] {
            let f = (0..<n).map {
                Stub(id: $0, cat: ["politics", "politics", "basketball", "politics",
                                   "tech", "baseball"][$0 % 6])
            }
            let out = FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                                breakNonSportsRuns: true, category: cat)
            XCTAssertEqual(out.count, n, "count preserved at n=\(n)")
            XCTAssertEqual(Set(out.map(\.id)), Set(f.map(\.id)), "id set preserved at n=\(n)")
        }
    }

    func testAllNonSportsSingleCategoryCannotBeImprovedAndDoesNotHang() {
        // Degenerate: nothing to interleave with. The guard must terminate and
        // return every card — it cannot invent variety that is not there.
        let f = (0..<30).map { Stub(id: $0, cat: "politics") }
        let out = FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                            breakNonSportsRuns: true, category: cat)
        XCTAssertEqual(out.count, 30)
        XCTAssertEqual(maxRun(out), 30, "no reordering can separate 30 identical categories")
    }

    func testAllSportsInputStillReturnedUnchangedWithGuardOn() {
        // The `nonSports.isEmpty` early return is pinned behavior
        // (`testAllSportsInputReturnedUnchanged`); the new flag must not alter it.
        let f = (0..<40).map { Stub(id: $0, cat: "basketball") }
        XCTAssertEqual(FeedInterleave.byCategory(f, sportsCategories: sportsCats,
                                                 breakNonSportsRuns: true, category: cat), f)
    }
}
