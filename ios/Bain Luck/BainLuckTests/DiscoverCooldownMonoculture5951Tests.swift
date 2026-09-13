import XCTest
@testable import Bain_Luck

/// #5951 — Discover must not hand the reader a page of the only categories he has
/// never touched.
///
/// Alex, 2026-09-13, on the installed build: Discover was "consistently entirely
/// UFC/F1/Cycling event cards with no images or context". The feed lane measured
/// the server the same hour and cleared it — four pages, 152 cards, page one
/// politics 10 / economics 7 / MLB 3 / tech 3 / entertainment 3 / weather 2 plus
/// six more sports, and zero UFC/F1/cycling among them. So the selection was the
/// client's.
///
/// The mechanism, and why it compounds instead of self-correcting:
/// `DiscoverInteractionProfile.score(for:)` returns **0 for a category the reader
/// has never engaged with** and a NEGATIVE score for one he has swiped away.
/// `suppresses` fires at -3, three left-swipes. The old cooldown stage then sorted
/// the page into two blocks — everything not suppressed, then a backfill — so the
/// block that led the page was, by construction, *the categories he had never
/// touched*. A reader who swipes the sports he follows is served the sports he
/// does not, for the 14 days `cooldownTTL` lives, and every swipe at the result
/// widens the set.
///
/// The fix is in `DiscoverView.applyCooldownSink`: the stage sinks a cooled card a
/// bounded number of positions instead of partitioning the page. These tests pin
/// the defect's own arithmetic FIRST — a guard that only asserts the new rule
/// cannot tell you the old one was ever broken.
final class DiscoverCooldownMonoculture5951Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-09-13T17:00:00Z")!

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func card(_ id: Int, category: String) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: Data("""
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Market \(id)?",
            "llm_sport_category": "\(category)",
            "source": "kalshi",
            "status": "open",
            "resolution_date": "2027-01-01T00:00:00Z",
            "top_outcomes": [{"id": \(id * 10), "name": "Yes", "probability": 0.5, "rank": 1}],
            "outcome_count": 1
          }
        }
        """.utf8))
    }

    private func categoryOf(_ item: FeedItem) -> String { DiscoverCategory.of(item) }

    /// Alex's reader, as a page: the categories he follows lead (that is what the
    /// server ranked), and the three he has never engaged with are scattered
    /// through it the way the feed lane measured them — a few cards, not a page.
    ///
    /// `mma` and `motorsports` are the tokens `DiscoverCategory.domainTokens` maps
    /// `ufc` and `f1` onto, so this page is his report in the app's own vocabulary
    /// rather than in the words of the bug report.
    private func alexsPage() throws -> [FeedItem] {
        let census: [(String, Int)] = [
            ("politics", 10), ("economics", 7), ("baseball", 3), ("tech", 3),
            ("entertainment", 3), ("weather", 2), ("soccer", 2), ("golf", 2),
            ("hockey", 1), ("tennis", 1),
            ("mma", 3), ("motorsports", 2), ("cycling", 1),
        ]
        var items: [FeedItem] = []
        var id = 1
        // Interleaved, not blocked: a page that served all thirteen categories in
        // thirteen runs would make ANY ordering rule look diverse at the top.
        var buckets = census.map { (category: $0.0, remaining: $0.1) }
        while buckets.contains(where: { $0.remaining > 0 }) {
            for i in buckets.indices where buckets[i].remaining > 0 {
                items.append(try card(id, category: buckets[i].category))
                buckets[i].remaining -= 1
                id += 1
            }
        }
        return items
    }

    /// The profile of a reader who has swiped in the categories he follows and has
    /// never once interacted with UFC, F1 or cycling.
    private func alexsProfile() -> DiscoverInteractionProfile {
        DiscoverInteractionProfile.forTesting(
            scores: [
                "politics": -4, "economics": -4, "baseball": -4, "tech": -4,
                "entertainment": -4, "weather": -4, "soccer": -4, "golf": -4,
                "hockey": -4, "tennis": -4,
            ],
            recordedAt: now
        )
    }

    private let neverEngaged: Set<String> = ["mma", "motorsports", "cycling"]

    // MARK: - The defect, pinned before the fix is asserted

    /// The rule that shipped: partition into kept + backfill. On this page and this
    /// profile it puts the six never-engaged cards at the head of the feed — which
    /// is exactly what Alex saw. Written out rather than referenced so that if
    /// someone restores the partition, this test says what they restored.
    func testThePartitionRuleLeadsWithTheCategoriesTheReaderNeverTouched() throws {
        let page = try alexsPage()
        let profile = alexsProfile()

        let partitioned = DiscoverView.applyFloor(
            to: page,
            keeping: { !profile.suppresses(category: self.categoryOf($0), now: self.now) },
            backfillPriority: { profile.score(for: self.categoryOf($0), now: self.now) },
            neverBackfill: { _ in false }
        )

        let leadCategories = partitioned.prefix(6).map { categoryOf($0) }
        XCTAssertTrue(
            leadCategories.allSatisfy { neverEngaged.contains($0) },
            "the defect: the head of the page is UFC/F1/cycling — \(leadCategories)")
    }

    // MARK: - The fix

    /// The same page and the same profile through the stage the app now runs: the
    /// never-engaged cards no longer own the top of the feed.
    ///
    /// Asserted as "the lead is not a monoculture", not as a fixed running order —
    /// an assertion on the exact sequence would pin the sink's arithmetic rather
    /// than the reader's complaint, and would have to be rewritten by anyone who
    /// tunes `cooldownSinkPositions`.
    func testTheSinkDoesNotHandTheReaderAPageOfWhatHeNeverTouched() throws {
        let page = try alexsPage()
        let profile = alexsProfile()

        let rendered = DiscoverView.applyCooldownSink(
            to: page,
            isCooled: { profile.suppresses(category: self.categoryOf($0), now: self.now) }
        )

        XCTAssertEqual(rendered.count, page.count, "nothing removed")

        let lead = rendered.prefix(6).map { categoryOf($0) }
        XCTAssertFalse(
            lead.allSatisfy { neverEngaged.contains($0) },
            "the head of the page is no longer a never-engaged monoculture — \(lead)")
        XCTAssertGreaterThanOrEqual(
            lead.filter { !neverEngaged.contains($0) }.count, 3,
            "at least half the opening cards are categories the reader actually reads — \(lead)")

        // And the reader's signal is still being honoured somewhere: the six
        // never-engaged cards sit higher, on average, than they did as served.
        let servedIndex = Dictionary(uniqueKeysWithValues:
            page.enumerated().map { (DiscoverView.feedItemId($0.element), $0.offset) })
        let moved = rendered.enumerated()
            .filter { neverEngaged.contains(categoryOf($0.element)) }
            .map { servedIndex[DiscoverView.feedItemId($0.element)]! - $0.offset }
        XCTAssertTrue(
            moved.allSatisfy { $0 >= 0 } && moved.contains(where: { $0 > 0 }),
            "never-engaged cards rise (or hold), because everything else sank — \(moved)")
    }

    /// The whole presentation pipeline for a reader who is BOTH swiping cards away
    /// and carrying a cooled profile: a dismissal still means dismissed.
    ///
    /// This is the half a reordering fix is most likely to break — the sink sees
    /// only what the dismiss stage passed it, and the two stages are composed in
    /// `filteredItems` in an order no unit test of either one alone can prove.
    func testADismissedCardStaysDismissedThroughTheSink() throws {
        let page = try alexsPage()
        let profile = alexsProfile()
        let epoch = now.timeIntervalSince1970

        // Three cards swiped away seconds ago — one of them a never-engaged card,
        // which is the one the old rule would have promoted straight back.
        let swiped = [page[0], page[1], page[10]]
        var dismissedAt: [String: TimeInterval] = [:]
        for item in swiped { dismissedAt[DiscoverView.feedItemId(item)] = epoch - 5 }

        // Through `personalize`, which is the composition the view runs — not the
        // two stages called by hand in the order this test happens to believe in.
        let rendered = DiscoverView.personalize(
            page,
            dismissedAt: dismissedAt,
            now: epoch,
            isCooled: { profile.suppresses(category: self.categoryOf($0), now: self.now) }
        )

        let renderedIds = Set(rendered.map { DiscoverView.feedItemId($0) })
        for item in swiped {
            XCTAssertFalse(
                renderedIds.contains(DiscoverView.feedItemId(item)),
                "a card swiped away five seconds ago is not on the page (#5453)")
        }
        XCTAssertEqual(
            rendered.count, page.count - swiped.count,
            "and nothing else left with them")
    }

    // MARK: - The wiring

    /// `filteredItems` is a private computed property on a `View`, so no unit test
    /// can drive it — which means the one line that chooses between the sink and
    /// the partition is the one line none of the tests above can see. The
    /// mutation battery proved it: restoring the partition *at the call site*
    /// survived every behavioural guard here.
    ///
    /// So this is a source scan, and it is worth exactly what its vacuity checks
    /// are worth — both are asserted before the claim.
    func testTheViewWiresTheSinkAndNotThePartition() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        // Vacuity 1: this is the file that holds the stage.
        XCTAssertTrue(
            source.contains("static func applyCooldownSink"),
            "the sink has moved out of DiscoverView — re-aim this scan")
        // Vacuity 2: the property this scan is about still exists under that name.
        guard let start = source.range(of: "private var filteredItems: [FeedItem] {") else {
            return XCTFail("filteredItems has been renamed — re-aim this scan")
        }
        guard let end = source.range(of: "\n    }\n", range: start.upperBound..<source.endIndex) else {
            return XCTFail("could not find the end of filteredItems — re-aim this scan")
        }
        let body = String(source[start.upperBound..<end.lowerBound])

        XCTAssertTrue(
            body.contains("Self.personalize("),
            "filteredItems must run the personalization pipeline (#5951)")
        XCTAssertFalse(
            body.contains("backfillPriority:"),
            "filteredItems partitions the page by cooldown again — that is #5951")
    }
}
