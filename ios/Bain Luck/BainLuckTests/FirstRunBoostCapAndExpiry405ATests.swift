import XCTest
@testable import Bain_Luck

@MainActor
final class FirstRunBoostCapAndExpiry405ATests: XCTestCase {

    private func makeDefaults(_ name: String = UUID().uuidString) -> UserDefaults {
        let suiteName = "FirstRunBoost405A.\(name)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    private func makeFeedFutures(id: Int, name: String, category: String, probability: Double = 0.55) throws -> FeedItem {
        let json = """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"\(name)","llm_sport_category":"\(category)","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"Yes","probability":\(probability),"rank":1}],"outcome_count":1}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedItem.self, from: Data(json.utf8))
    }

    // MARK: - One-week window lifecycle

    func testSaveStampsTimestampAndExpiresAfterExactlySevenDays() {
        let defaults = makeDefaults()
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000) // ~Nov 2026
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["economics"],
            boostedTerms: [],
            boostedMarketIds: []
        )
        prefs.save(defaults: defaults, now: savedAt)

        let loaded = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertEqual(loaded.savedAtEpoch, savedAt.timeIntervalSince1970)
        XCTAssertEqual(FirstRunPreferences212A.boostDurationSeconds, 7 * 24 * 60 * 60)

        // Active from save through one second before the 7-day mark.
        XCTAssertTrue(loaded.isBoostActive(now: savedAt))
        XCTAssertTrue(loaded.isBoostActive(now: savedAt.addingTimeInterval(604_799)))

        // Stops permanently at exact +7 days and beyond.
        XCTAssertFalse(loaded.isBoostActive(now: savedAt.addingTimeInterval(604_800)))
        XCTAssertFalse(loaded.isBoostActive(now: savedAt.addingTimeInterval(8 * 24 * 60 * 60)))
    }

    func testLegacyPreferencesWithoutSavedTimestampDoNotBoostAndResaveStartsFreshWeek() throws {
        let defaults = makeDefaults()
        let legacyJSON = #"{"boostedCategories":["politics"],"boostedTerms":["Election"],"boostedMarketIds":[42]}"#
        defaults.set(Data(legacyJSON.utf8), forKey: FirstRunStorageKeys212A.localPreferencesKey)

        let legacyLoaded = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertFalse(legacyLoaded.isEmpty)
        XCTAssertNil(legacyLoaded.savedAtEpoch)
        XCTAssertFalse(legacyLoaded.isBoostActive(now: Date(timeIntervalSince1970: 1_795_500_000)))

        let reSaveTime = Date(timeIntervalSince1970: 1_796_000_000)
        legacyLoaded.save(defaults: defaults, now: reSaveTime)
        let refreshed = FirstRunPreferences212A.load(defaults: defaults)
        XCTAssertEqual(refreshed.savedAtEpoch, reSaveTime.timeIntervalSince1970)
        XCTAssertTrue(refreshed.isBoostActive(now: reSaveTime.addingTimeInterval(6 * 24 * 60 * 60)))
        XCTAssertFalse(refreshed.isBoostActive(now: reSaveTime.addingTimeInterval(7 * 24 * 60 * 60)))
    }

    // MARK: - Cap: up to 3 per picked kind inside the first 10 seats

    func testPromoteCapsOnePickedKindAtThreeOfFirstTenSeatsEvenWithSixMatchesLater() {
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000)
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["economics"],
            boostedTerms: [],
            boostedMarketIds: [],
            savedAtEpoch: savedAt.timeIntervalSince1970
        )

        struct Row: Equatable {
            let id: Int
            let kind: String
        }

        // First 10 rows are non-picked ("politics" 1...10); rows 11...16 are picked ("economics" 11...16).
        let input = (1...10).map { Row(id: $0, kind: "politics") }
            + (11...16).map { Row(id: $0, kind: "economics") }

        let result = FirstRunDiscoverBoost212A.promotePreferredItems(
            input,
            preferences: prefs,
            now: savedAt.addingTimeInterval(60),
            kindOf: { $0.kind }
        ) { row, p in
            p.boostedCategories.contains(row.kind)
        }

        XCTAssertEqual(result.count, input.count, "must never drop items")
        XCTAssertEqual(Set(result.map(\.id)), Set(input.map(\.id)), "must never duplicate items")

        let firstTen = Array(result.prefix(10))
        let firstTenEcon = firstTen.filter { $0.kind == "economics" }
        XCTAssertEqual(firstTenEcon.map(\.id), [11, 12, 13], "only 3 picked cards enter the first 10 seats")
        XCTAssertEqual(firstTen.filter { $0.kind == "politics" }.map(\.id), [1, 2, 3, 4, 5, 6, 7])
        XCTAssertEqual(Array(result.dropFirst(10)).map(\.id), [8, 9, 10, 14, 15, 16])
    }

    func testPromoteCapsWhenSixPickedMatchesAlreadyOccupyFrontOfFeed() {
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000)
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["tech"],
            boostedTerms: [],
            boostedMarketIds: [],
            savedAtEpoch: savedAt.timeIntervalSince1970
        )

        struct Row: Equatable {
            let id: Int
            let kind: String
        }

        // First 6 rows are all picked ("tech"), followed by 10 unpicked ("politics").
        let input = (1...6).map { Row(id: $0, kind: "tech") }
            + (7...16).map { Row(id: $0, kind: "politics") }

        let result = FirstRunDiscoverBoost212A.promotePreferredItems(
            input,
            preferences: prefs,
            now: savedAt.addingTimeInterval(60),
            kindOf: { $0.kind }
        ) { row, p in
            p.boostedCategories.contains(row.kind)
        }

        let firstTen = Array(result.prefix(10))
        XCTAssertEqual(firstTen.filter { $0.kind == "tech" }.map(\.id), [1, 2, 3])
        XCTAssertEqual(firstTen.filter { $0.kind == "politics" }.count, 7)
        XCTAssertEqual(result.dropFirst(10).prefix(3).map(\.id), [4, 5, 6], "4th+ match sits behind the first 10 seats")
    }

    func testPromoteCapsEachPickedKindIndependentlyAndPreservesExpiredOrder() {
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000)
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["economics", "weather"],
            boostedTerms: [],
            boostedMarketIds: [],
            savedAtEpoch: savedAt.timeIntervalSince1970
        )

        struct Row: Equatable {
            let id: Int
            let kind: String
        }

        let input = (1...6).map { Row(id: $0, kind: "politics") }
            + (7...11).map { Row(id: $0, kind: "economics") }
            + (12...16).map { Row(id: $0, kind: "weather") }

        let active = FirstRunDiscoverBoost212A.promotePreferredItems(
            input,
            preferences: prefs,
            now: savedAt.addingTimeInterval(3 * 24 * 60 * 60),
            kindOf: { $0.kind }
        ) { row, p in
            p.boostedCategories.contains(row.kind)
        }

        let firstTen = Array(active.prefix(10))
        XCTAssertEqual(firstTen.filter { $0.kind == "economics" }.map(\.id), [7, 8, 9])
        XCTAssertEqual(firstTen.filter { $0.kind == "weather" }.map(\.id), [12, 13, 14])
        XCTAssertEqual(firstTen.filter { $0.kind == "politics" }.map(\.id), [1, 2, 3, 4])

        // After 1 week, order reverts identically to the unboosted feed.
        let expired = FirstRunDiscoverBoost212A.promotePreferredItems(
            input,
            preferences: prefs,
            now: savedAt.addingTimeInterval(7 * 24 * 60 * 60),
            kindOf: { $0.kind }
        ) { row, p in
            p.boostedCategories.contains(row.kind)
        }
        XCTAssertEqual(expired, input)
    }

    func testPromoteStillFillsFirstTenWhenFewerThanSevenUnpickedItemsExist() {
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000)
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["tech"],
            boostedTerms: [],
            boostedMarketIds: [],
            savedAtEpoch: savedAt.timeIntervalSince1970
        )

        struct Row: Equatable {
            let id: Int
            let kind: String
        }

        // Only 2 unpicked items exist across the whole 12-item deck.
        let input = (1...10).map { Row(id: $0, kind: "tech") }
            + [Row(id: 11, kind: "politics"), Row(id: 12, kind: "politics")]

        let result = FirstRunDiscoverBoost212A.promotePreferredItems(
            input,
            preferences: prefs,
            now: savedAt,
            kindOf: { $0.kind }
        ) { row, p in
            p.boostedCategories.contains(row.kind)
        }

        XCTAssertEqual(Array(result.prefix(10)).count, 10)
        XCTAssertEqual(Set(result.map(\.id)), Set(input.map(\.id)))
        XCTAssertEqual(Array(result.prefix(5)).map(\.id), [1, 2, 3, 11, 12], "unpicked items move ahead of deferred excess")
    }

    // MARK: - DiscoverView integration (both flat and opening/continuation paths)

    func testDiscoverViewPresentationCapsFirstRunBoostAtThreeInFirstTenAndStopsAtOneWeek() throws {
        let savedAt = Date(timeIntervalSince1970: 1_795_500_000)
        let prefs = FirstRunPreferences212A(
            boostedCategories: ["economics"],
            boostedTerms: [],
            boostedMarketIds: [],
            savedAtEpoch: savedAt.timeIntervalSince1970
        )

        var rawItems: [FeedItem] = []
        for idx in 1...10 {
            let cat = idx.isMultiple(of: 2) ? "politics" : "weather"
            rawItems.append(try makeFeedFutures(id: idx, name: "Distinct Nonpick Topic \(idx)?", category: cat))
        }
        for idx in 11...16 {
            rawItems.append(try makeFeedFutures(id: idx, name: "Distinct Economy Question \(idx)?", category: "economics"))
        }

        let unboosted = DiscoverView.resolveGroupedPresentation(
            rawItems: rawItems,
            cached: nil,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            firstRunPreferences: .empty,
            now: savedAt.addingTimeInterval(100)
        )
        let unboostedIds = unboosted.items.map(\.id)

        let active = DiscoverView.resolveGroupedPresentation(
            rawItems: rawItems,
            cached: nil,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            firstRunPreferences: prefs,
            now: savedAt.addingTimeInterval(604_799)
        )
        let activeFirstTenEcon = active.items.prefix(10).filter {
            DiscoverView.primaryFeedItem($0)?.futures?.llmSportCategory == "economics"
        }
        XCTAssertEqual(activeFirstTenEcon.count, 3, "only 3 picked cards take first-10 Discover seats")
        XCTAssertEqual(active.items.count, unboosted.items.count)

        let expired = DiscoverView.resolveGroupedPresentation(
            rawItems: rawItems,
            cached: nil,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            firstRunPreferences: prefs,
            now: savedAt.addingTimeInterval(604_800)
        )
        XCTAssertEqual(expired.items.map(\.id), unboostedIds, "at +7 days boost stops and matches unboosted order")

        // Also exercise the opening + continuation section partition path.
        let sectionedActive = DiscoverView.resolveGroupedPresentation(
            rawItems: rawItems,
            cached: nil,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            firstRunPreferences: prefs,
            now: savedAt.addingTimeInterval(3600)
        ) { item in
            (item.futures?.id ?? 0) <= 10 ? .opening : .continuation
        }
        let sectionedFirstTenEcon = sectionedActive.items.prefix(10).filter {
            DiscoverView.primaryFeedItem($0)?.futures?.llmSportCategory == "economics"
        }
        XCTAssertEqual(sectionedFirstTenEcon.count, 3, "sectioned opening+continuation caps picked kind at 3 in first 10 seats")
    }
}
