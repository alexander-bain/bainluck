import XCTest
@testable import Bain_Luck

/// #5951, the client half — A PULL-TO-REFRESH HANDED BACK EVERY CARD THE READER
/// HAD JUST SWIPED AWAY.
///
/// The server half of this issue (`fix(discover): a swiped concept or tournament
/// card stays swiped`) makes a dismissal survive the next feed BUILD. Native
/// undid that one gesture later: `refreshFeed` — the path behind pull-to-refresh
/// AND both end-card Refresh buttons — opened with
///
///     dismissedAt.removeAll()
///
/// so the in-memory store emptied and every card of this sitting came back on
/// the same screen. Alex's production evidence for #5951 is ten native `unlike`
/// rows in 21 seconds with NINE of them on one card; this is the client path
/// that can produce that shape without the reader doing anything unusual.
///
/// The clear predates the floor. #1221 exists so a heavy dismiss history can no
/// longer collapse the page (`applyFloor` backfills to `feedFloor`), so emptying
/// the store bought nothing the floor does not already buy. Web has never done
/// it — `discover/page.tsx` keeps its dismissals across a refresh and resets only
/// the paging state — so this is also the two surfaces agreeing again.
///
/// `now` is injected throughout (gotcha #44): no assertion here branches on the
/// wall clock.
final class ARefreshDoesNotUndoASwipe5951Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-09-13T12:00:00Z")!
        .timeIntervalSince1970

    private static let day: TimeInterval = 24 * 3600

    // MARK: - 🔴 The defect

    func testARefreshKeepsTheCardsTheReaderJustSwipedAway() {
        let store = swipes(ids: [1, 2, 3, 4, 5, 6], at: now - 30)

        let after = DiscoverView.dismissStoreAfterRefresh(store, now: now)

        XCTAssertEqual(
            Set(after.keys), Set(store.keys),
            "a refresh asks the server for more material; it is not the reader "
            + "withdrawing six swipes he made half a minute ago")
        XCTAssertEqual(after, store, "and their timestamps are untouched")
    }

    /// The claim a reader can see: the six cards are still gone from the page the
    /// refresh renders. Asserted through the dismiss stage the app actually runs,
    /// not through the store alone — a store that survives and a stage that
    /// ignores it would still put the cards back.
    func testTheSixSwipedCardsAreStillMissingFromTheRefreshedPage() throws {
        let page = try productionShapedPage()
        let swiped = [1, 2, 3, 4, 5, 6]
        let store = swipes(ids: swiped, at: now - 30)

        let rendered = DiscoverView.applyDismissFloor(
            to: page,
            dismissedAt: DiscoverView.dismissStoreAfterRefresh(store, now: now),
            now: now
        )

        XCTAssertEqual(rendered.count, page.count - swiped.count)
        for id in swiped {
            XCTAssertFalse(
                rendered.contains { DiscoverView.feedItemId($0) == "futures-\(id)" },
                "futures-\(id) was swiped away 30 seconds ago and must not be "
                + "on the page the refresh drew")
        }
    }

    /// Non-vacuity: the same composition under what `refreshFeed` used to hand
    /// back. Without this arm the assertion above passes on any page whose cards
    /// simply were not dismissed, forever.
    func testTheMeasurementCanActuallySeeTheDefect() throws {
        let page = try productionShapedPage()
        let cleared: [String: TimeInterval] = [:]   // dismissedAt.removeAll()

        let rendered = DiscoverView.applyDismissFloor(
            to: page, dismissedAt: cleared, now: now
        )

        XCTAssertEqual(
            rendered.count, page.count,
            "the old behaviour: every one of the six comes back")
    }

    // MARK: - 🟢 What the refresh must still do

    /// The store decays (#1221). A session that is never relaunched must not be
    /// able to hold a swipe past its 14 days, so the refresh prunes exactly what
    /// `loadDismissed` prunes at launch.
    func testARefreshAgesOutASwipePastItsFourteenDays() {
        let store = swipes(ids: [1], at: now - 15 * Self.day)
            .merging(swipes(ids: [2], at: now - 13 * Self.day)) { a, _ in a }

        let after = DiscoverView.dismissStoreAfterRefresh(store, now: now)

        XCTAssertNil(after["futures-1"], "15 days is past the TTL")
        XCTAssertNotNil(after["futures-2"], "13 days is not — it is still a downrank")
    }

    /// #5453 composed with the refresh: the floor is allowed to come up short
    /// rather than meet itself out of this sitting's rejects. The end state is
    /// honest; the reader's own swipes coming back is not.
    func testAShortPageIsNotRebuiltFromThisSittingsSwipes() throws {
        let page = try Array(productionShapedPage().prefix(30))
        let swiped = Array(1...25)
        let store = swipes(ids: swiped, at: now - 60)

        let rendered = DiscoverView.applyDismissFloor(
            to: page,
            dismissedAt: DiscoverView.dismissStoreAfterRefresh(store, now: now),
            now: now
        )

        XCTAssertLessThan(
            rendered.count, DiscoverView.feedFloor,
            "the floor is 28 and only 5 cards survive — it must run short, not "
            + "recycle a swipe from 60 seconds ago")
        XCTAssertEqual(rendered.count, 5)
    }

    /// The other direction (#1091 / notice 43): a swipe that has aged out of the
    /// grace window is a decayed preference again, and the floor may use it.
    func testASwipeOlderThanTheGraceWindowStillBackfillsAShortPage() throws {
        let page = try Array(productionShapedPage().prefix(30))
        let store = swipes(
            ids: Array(1...25),
            at: now - DiscoverView.backfillGraceWindow - 60
        )

        let rendered = DiscoverView.applyDismissFloor(
            to: page,
            dismissedAt: DiscoverView.dismissStoreAfterRefresh(store, now: now),
            now: now
        )

        XCTAssertEqual(
            rendered.count, DiscoverView.feedFloor,
            "an hour-old swipe is the soft, decaying downrank #1221 designed")
    }

    /// The boundary itself, pinned against the OTHER two prunes of the same
    /// store: `loadDismissed` keeps `value >= cutoff` at launch and
    /// `saveDismissed` keeps `value >= cutoff` on write. A refresh that used `>`
    /// would drop a swipe those two keep, so the same store would hold different
    /// cards depending on which of three code paths last touched it.
    func testTheRefreshPrunesOnTheSameBoundaryAsLaunchAndSave() {
        let exactlyAtTheCutoff = swipes(ids: [1], at: now - 14 * Self.day)

        XCTAssertNotNil(
            DiscoverView.dismissStoreAfterRefresh(exactlyAtTheCutoff, now: now)["futures-1"],
            "14 days to the second is inclusive here because it is inclusive in "
            + "loadDismissed and saveDismissed — three prunes, one boundary")
    }

    func testAReaderWhoHasSwipedNothingIsUnaffected() {
        XCTAssertTrue(DiscoverView.dismissStoreAfterRefresh([:], now: now).isEmpty)
    }

    // MARK: - Reach

    /// The helper above is only worth its tests if the refresh path calls it.
    /// `refreshFeed` is a private method on a `View`, so this is the one claim in
    /// the file that has to be read off the source rather than executed.
    func testTheRefreshPathUsesTheHelperAndNoLongerEmptiesTheStore() throws {
        let view = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        let source = try String(contentsOf: view, encoding: .utf8)
        // Comment lines are stripped: the helper's own doc comment quotes the
        // defect verbatim to say what it replaced, and a scan that reads prose
        // would fail on the explanation of the fix.
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        // The needle is the DECLARATION PREFIX, not the whole signature. This
        // assertion exists to prove the strip above left code standing, not to
        // pin `refreshFeed`'s parameter list — and pinning the list is what it
        // accidentally did: #1472 gave the method a `returningToTopWith:`
        // argument and reddened this line, which says nothing about whether the
        // dismiss store is still aged through the helper. The two assertions
        // below are this test's actual subject and are untouched.
        XCTAssertTrue(
            code.contains("private func refreshFeed("),
            "the strip must leave the code standing — an over-eager filter would "
            + "make every assertion below pass on an empty string")
        XCTAssertTrue(
            code.contains("dismissedAt = Self.dismissStoreAfterRefresh(dismissedAt)"),
            "refreshFeed must age the store through the tested helper")
        XCTAssertFalse(
            code.contains("dismissedAt.removeAll()"),
            "emptying the dismiss store anywhere is the #5951 defect: it hands "
            + "the reader back every card he swiped away this sitting")
    }

    // MARK: - Fixtures

    /// `feedItemId` for a futures card is `futures-<id>`, which is what the swipe
    /// path stores and what the dismiss stage looks up.
    private func swipes(ids: [Int], at stamp: TimeInterval) -> [String: TimeInterval] {
        Dictionary(uniqueKeysWithValues: ids.map { ("futures-\($0)", stamp) })
    }

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// An open, well-dated futures card — nothing here is stale, so anything
    /// these tests remove was removed by the dismiss stage and not by the
    /// lifecycle gate.
    private func card(_ id: Int) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: Data("""
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Market \(id)?",
            "llm_sport_category": "politics",
            "source": "kalshi",
            "status": "open",
            "resolution_date": "2027-01-01T00:00:00Z",
            "top_outcomes": [{"id": \(id * 10), "name": "Yes", "probability": 0.5, "rank": 1}],
            "outcome_count": 1
          }
        }
        """.utf8))
    }

    /// 50 cards, the page size `/api/feed?limit=50` serves.
    private func productionShapedPage() throws -> [FeedItem] {
        try (1...50).map { try card($0) }
    }
}
