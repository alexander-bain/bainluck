import XCTest
@testable import Bain_Luck

/// #1221 part two — no client-side filter may starve a healthy Discover page.
///
/// The first half of #1221 floored and expired the DISMISS store. The category
/// cooldown got neither guard, and it is the one Alex hit: his phone showed
/// **3 cards** while `GET /api/feed?limit=50` was handing the client 50. The
/// cooldown filter dropped every card in a cooled-down category and only fell
/// back when the result was *empty*, and the profile behind it never decayed —
/// three left-swipes blacklisted a category for the life of the install.
///
/// Two contracts are pinned here, and BOTH are needed: the floor stops a page
/// from collapsing today, the decay stops the profile from re-collapsing it
/// tomorrow. `now` is injected throughout (gotcha #44).
final class DiscoverClientFilterFloorTests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-09-03T12:00:00Z")!

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// A futures card in `category`. Open, dated well past `now`, one outcome —
    /// nothing here is stale, so anything these tests remove was removed by the
    /// filter under test and not by the lifecycle gate.
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

    /// The live page of 2026-09-03 in miniature: the same 14 categories in the
    /// same proportions the server served (politics 15, entertainment 6, soccer 5,
    /// hockey 5, tech 4, baseball 4, weather 2, motorsports 2, geopolitics 2, and
    /// one each of cycling, football, lacrosse, golf, tennis) — 50 cards.
    private func productionShapedPage() throws -> [FeedItem] {
        let census: [(String, Int)] = [
            ("politics", 15), ("entertainment", 6), ("soccer", 5), ("hockey", 5),
            ("tech", 4), ("baseball", 4), ("weather", 2), ("motorsports", 2),
            ("geopolitics", 2), ("cycling", 1), ("football", 1), ("lacrosse", 1),
            ("golf", 1), ("tennis", 1),
        ]
        var items: [FeedItem] = []
        var id = 1
        for (category, count) in census {
            for _ in 0..<count {
                items.append(try card(id, category: category))
                id += 1
            }
        }
        return items
    }

    private func categoryOf(_ item: FeedItem) -> String { DiscoverCategory.of(item) }

    // MARK: - The reported defect

    /// The exact shape of Alex's report: a profile that has cooled the 11 biggest
    /// categories leaves 3 uncooled cards out of 50. Before the floor that WAS the
    /// rendered feed (the old fallback only fired at zero). Now it is the floor.
    func testCooledDownProfileCannotCutAFiftyCardPageToThree() throws {
        let page = try productionShapedPage()
        XCTAssertEqual(page.count, 50, "fixture must match the measured page size")

        let cooled = [
            "politics", "entertainment", "soccer", "hockey", "tech", "baseball",
            "weather", "motorsports", "geopolitics", "cycling", "football",
        ]
        let profile = DiscoverInteractionProfile.forTesting(
            scores: Dictionary(uniqueKeysWithValues: cooled.map { ($0, -4.0) }),
            recordedAt: now
        )

        // What the cooldown alone would leave — the measured "3".
        let uncooled = page.filter { !profile.suppresses(category: categoryOf($0), now: now) }
        XCTAssertEqual(uncooled.count, 3, "the defect's arithmetic, pinned")

        let rendered = DiscoverView.applyFloor(
            to: page,
            keeping: { !profile.suppresses(category: self.categoryOf($0), now: self.now) },
            backfillPriority: { profile.score(for: self.categoryOf($0), now: self.now) }
        )
        XCTAssertGreaterThanOrEqual(
            rendered.count, DiscoverView.feedFloor,
            "a healthy 50-card page must never render below the feed floor")

        // SHOWABLE-1 gate G1, stated as a number and not as a constant: a floor
        // of 8 still let this page lose 84% of itself, which is not "Discover
        // shows the feed the API sends". Written literally so raising the floor
        // is a decision someone makes, not something a refactor does silently.
        XCTAssertGreaterThanOrEqual(
            rendered.count, 28,
            "G1: a 50-card page with a heavily cooled profile still shows ≥28 cards")

        // And the cooldown is still doing its job: every uncooled card leads.
        XCTAssertEqual(
            rendered.prefix(3).filter { !profile.suppresses(category: categoryOf($0), now: now) }.count,
            3,
            "the 3 uncooled cards lead; the floor sinks the cooled ones, it does not re-rank them up")
    }

    /// The floor is a floor, not a cap: an uncooled page renders in full.
    func testFloorNeverTruncatesAPageTheFilterKept() throws {
        let page = try productionShapedPage()
        let profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        let rendered = DiscoverView.applyFloor(
            to: page,
            keeping: { !profile.suppresses(category: self.categoryOf($0), now: self.now) },
            backfillPriority: { _ in 0 }
        )
        XCTAssertEqual(rendered.count, 50)
    }

    /// A page that is genuinely smaller than the floor is not padded with
    /// nothing — the floor can only ever return cards the API actually sent.
    func testShortPageIsNotInflated() throws {
        let page = try (1...3).map { try card($0, category: "politics") }
        let profile = DiscoverInteractionProfile.forTesting(scores: ["politics": -4], recordedAt: now)
        let rendered = DiscoverView.applyFloor(
            to: page,
            keeping: { !profile.suppresses(category: self.categoryOf($0), now: self.now) },
            backfillPriority: { _ in 0 }
        )
        XCTAssertEqual(rendered.count, 3, "backfill is bounded by what was served")
    }

    /// The profile still decides WHICH cards come back: least-cooled first, so a
    /// cooldown remains a downrank even when the floor overrides it.
    func testBackfillPrefersTheLeastCooledCategory() throws {
        // The page has to be bigger than the floor for the ORDER to be
        // observable at all: 1 uncooled + 20 hard-cooled + 20 barely-cooled = 41,
        // so the floor backfills 27 of the 40 removed cards and has to choose.
        var page: [FeedItem] = []
        page.append(try card(1, category: "tennis"))                            // not cooled
        for id in 2...21 { page.append(try card(id, category: "politics")) }    // hard cooled
        for id in 22...41 { page.append(try card(id, category: "soccer")) }     // barely cooled
        let profile = DiscoverInteractionProfile.forTesting(
            scores: ["politics": -9, "soccer": -3.1], recordedAt: now)

        let rendered = DiscoverView.applyFloor(
            to: page,
            keeping: { !profile.suppresses(category: self.categoryOf($0), now: self.now) },
            backfillPriority: { profile.score(for: self.categoryOf($0), now: self.now) }
        )
        XCTAssertEqual(rendered.count, DiscoverView.feedFloor)
        XCTAssertEqual(categoryOf(rendered[0]), "tennis", "the kept card still leads")
        let backfilled = rendered.dropFirst().map { categoryOf($0) }
        XCTAssertTrue(
            backfilled.allSatisfy { $0 == "soccer" || $0 == "politics" }, "\(backfilled)")
        XCTAssertEqual(
            backfilled.prefix(20).filter { $0 == "soccer" }.count, 20,
            "every barely-cooled soccer card returns before any hard-cooled politics card")
    }

    /// The group-collapse floor is NOT the subtractive-filter floor, and must not
    /// be quietly unified with it: it is met by expanding ladder groups back into
    /// singles, so chasing G1's card count there would re-flood page one with the
    /// near-duplicates grouping exists to remove.
    func testGroupExpansionFloorStaysBelowTheFilterFloor() {
        XCTAssertEqual(DiscoverView.groupExpansionFloor, 8)
        XCTAssertGreaterThan(DiscoverView.feedFloor, DiscoverView.groupExpansionFloor)
    }

    // MARK: - The cooldown expires

    func testThreeLeftSwipesCoolACategoryDown() {
        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        XCTAssertFalse(profile.suppresses(category: "politics", now: now))
        for i in 0..<3 {
            profile.record(category: "politics", action: .unlike,
                           now: now.addingTimeInterval(Double(i)))
        }
        XCTAssertTrue(profile.suppresses(category: "politics", now: now.addingTimeInterval(3)))
    }

    /// The defect the decay exists for: the ONLY inputs that raise a score are
    /// open/like/share, and all three require seeing a card in that category —
    /// which the suppression is exactly what prevents. Without decay a cooldown
    /// is unreachable-from-inside and therefore permanent.
    func testCooldownExpiresOnItsOwnWithinTheTTL() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["politics": -4], recordedAt: now)
        XCTAssertTrue(profile.suppresses(category: "politics", now: now))
        XCTAssertTrue(
            profile.suppresses(category: "politics", now: now.addingTimeInterval(24 * 3600)),
            "a day later it is still a cooldown — this is not an amnesty")
        XCTAssertFalse(
            profile.suppresses(
                category: "politics",
                now: now.addingTimeInterval(DiscoverInteractionProfile.cooldownTTL + 1)),
            "past the TTL the profile holds no opinion it has not re-earned")
        XCTAssertEqual(
            profile.score(
                for: "politics",
                now: now.addingTimeInterval(DiscoverInteractionProfile.cooldownTTL + 1)),
            0)
    }

    func testScoreDecaysMonotonicallyTowardZero() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["tech": -8], recordedAt: now)
        let day0 = profile.score(for: "tech", now: now)
        let day7 = profile.score(for: "tech", now: now.addingTimeInterval(7 * 24 * 3600))
        XCTAssertEqual(day0, -8, accuracy: 0.001)
        XCTAssertEqual(day7, -4, accuracy: 0.001, "half the window, half the magnitude")
        XCTAssertLessThan(abs(day7), abs(day0))
    }

    /// A backwards clock (timezone change, NTP correction) must not amplify a
    /// score into a deeper cooldown than the user ever earned.
    func testBackwardClockDoesNotAmplify() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["soccer": -4], recordedAt: now)
        XCTAssertEqual(profile.score(for: "soccer", now: now.addingTimeInterval(-90000)), -4)
    }

    /// Recording decays first, then applies — otherwise a stale score gets a
    /// fresh timestamp at its old magnitude and never ages out.
    func testRecordAppliesToTheDecayedScoreNotTheStoredOne() {
        var profile = DiscoverInteractionProfile.forTesting(scores: ["golf": -8], recordedAt: now)
        let later = now.addingTimeInterval(7 * 24 * 3600) // half-decayed to -4
        profile.record(category: "golf", action: .unlike, now: later)
        XCTAssertEqual(profile.score(for: "golf", now: later), -5, accuracy: 0.001)
    }

    func testAdjustmentIgnoresAFullyDecayedScore() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["hockey": 6], recordedAt: now)
        XCTAssertEqual(profile.adjustment(for: "hockey", now: now), 6, accuracy: 0.001)
        XCTAssertEqual(
            profile.adjustment(
                for: "hockey",
                now: now.addingTimeInterval(DiscoverInteractionProfile.cooldownTTL + 1)),
            0)
    }

    func testUnknownCategoryIsNeutral() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["politics": -9], recordedAt: now)
        XCTAssertEqual(profile.score(for: "curling", now: now), 0)
        XCTAssertFalse(profile.suppresses(category: "curling", now: now))
    }

    func testCategoryMatchIsCaseInsensitive() {
        let profile = DiscoverInteractionProfile.forTesting(scores: ["politics": -4], recordedAt: now)
        XCTAssertTrue(profile.suppresses(category: "Politics", now: now))
        XCTAssertTrue(profile.suppresses(category: "POLITICS", now: now))
    }
}
