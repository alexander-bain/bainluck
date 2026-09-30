import XCTest
@testable import Bain_Luck

/// #9648 — a left-swipe on a sports card is exact: it hides that card, and
/// teaches the local profile nothing about the sport.
///
/// The reader in the issue swiped away unrelated MLB games while opening every
/// Red Sox game. The profile summed those swipes into `baseball`, and three of
/// them cooled baseball down — sinking the Red Sox cards the reader wanted. The
/// server half (#9645) already scopes the same swipe to the card and its story;
/// these tests pin the phone's half, including scores saved before the fix.
final class DiscoverSportsNegativesExact9648Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-09-30T12:00:00Z")!

    // MARK: - UserDefaults isolation (the load path reads the real store)

    private var savedV2: Any?
    private var savedV1: Any?

    override func setUp() {
        super.setUp()
        let defaults = UserDefaults.standard
        savedV2 = defaults.object(forKey: DiscoverInteractionProfile.storageKey)
        savedV1 = defaults.object(forKey: DiscoverInteractionProfile.legacyStorageKey)
        defaults.removeObject(forKey: DiscoverInteractionProfile.storageKey)
        defaults.removeObject(forKey: DiscoverInteractionProfile.legacyStorageKey)
    }

    override func tearDown() {
        let defaults = UserDefaults.standard
        defaults.removeObject(forKey: DiscoverInteractionProfile.storageKey)
        defaults.removeObject(forKey: DiscoverInteractionProfile.legacyStorageKey)
        if let savedV2 { defaults.set(savedV2, forKey: DiscoverInteractionProfile.storageKey) }
        if let savedV1 { defaults.set(savedV1, forKey: DiscoverInteractionProfile.legacyStorageKey) }
        super.tearDown()
    }

    // MARK: - Fixtures

    private func decode(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func futuresJSON(_ id: Int, category: String) -> String {
        """
        { "type": "futures", "score": 90,
          "data": { "id": \(id), "name": "Market \(id)?", "llm_sport_category": "\(category)",
                    "source": "kalshi", "status": "open", "resolution_date": "2027-01-01T00:00:00Z",
                    "top_outcomes": [{"id": \(id * 10), "name": "Yes", "probability": 0.5, "rank": 1}],
                    "outcome_count": 1 } }
        """
    }

    private func eventJSON(_ id: Int, sport: String) -> String {
        """
        { "type": "event", "score": 90,
          "data": { "id": \(id), "sport": "\(sport)", "home_team": "Home", "away_team": "Away",
                    "status": "scheduled", "commence_time": "2026-10-01T23:00:00Z" } }
        """
    }

    private func futures(_ id: Int, category: String) throws -> FeedItem {
        try decode(futuresJSON(id, category: category))
    }

    private func event(_ id: Int, sport: String) throws -> FeedItem {
        try decode(eventJSON(id, sport: sport))
    }

    /// Record one left-swipe the way `DiscoverView.recordInteraction` does.
    private func swipeLeft(_ item: FeedItem, on profile: inout DiscoverInteractionProfile, at date: Date) {
        profile.record(
            category: DiscoverCategory.of(item),
            action: .unlike,
            onSportsCard: DiscoverCategory.isSportsFeedback(item),
            now: date
        )
    }

    private func swipeRight(_ item: FeedItem, on profile: inout DiscoverInteractionProfile, at date: Date) {
        profile.record(
            category: DiscoverCategory.of(item),
            action: .like,
            onSportsCard: DiscoverCategory.isSportsFeedback(item),
            now: date
        )
    }

    // MARK: - The reported shape

    /// Two Red Sox games liked, then five unrelated MLB games swiped away. The
    /// favoured relevance survives whole: before the fix `4 − 5 = −1`, which
    /// is below the ±2 dead band, so the Red Sox boost was gone and two more
    /// swipes would have cooled baseball down outright.
    func testUnrelatedMLBSwipesLeaveFavouredBaseballRelevanceIntact() throws {
        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        let redSoxGames = [try event(1, sport: "baseball_mlb"), try event(2, sport: "baseball_mlb")]
        for (i, game) in redSoxGames.enumerated() {
            swipeRight(game, on: &profile, at: now.addingTimeInterval(Double(i)))
        }
        for id in 10..<15 {
            swipeLeft(try event(id, sport: "baseball_mlb"), on: &profile, at: now.addingTimeInterval(Double(id)))
        }
        let t = now.addingTimeInterval(20)
        XCTAssertEqual(profile.adjustment(for: "baseball", now: t), 4, accuracy: 0.01,
                       "the two likes are the whole of baseball's score")
        XCTAssertFalse(profile.suppresses(category: "baseball", now: t))
    }

    func testSportsFuturesSwipesNeverCoolTheirSportDown() throws {
        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        for id in 0..<6 {
            swipeLeft(try futures(id, category: "baseball"), on: &profile, at: now.addingTimeInterval(Double(id)))
        }
        let t = now.addingTimeInterval(10)
        XCTAssertEqual(profile.score(for: "baseball", now: t), 0)
        XCTAssertEqual(profile.adjustment(for: "baseball", now: t), 0)
        XCTAssertFalse(profile.suppresses(category: "baseball", now: t))
    }

    /// A game whose sport-key root is not in any category set is still a game.
    /// This is the case the category rule alone misses and the call site's
    /// `onSportsCard` catches — the server answers it the same way
    /// (`item_type == "event"` is always sports).
    func testAGameInAnUnlistedSportIsStillASportsCard() throws {
        let handball = try event(1, sport: "handball_ehf")
        XCTAssertEqual(DiscoverCategory.of(handball), "handball")
        XCTAssertFalse(DiscoverCategory.sportsFeedbackCategories.contains("handball"),
                       "premise: only the event rule can protect this card")
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(handball))

        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        for i in 0..<4 { swipeLeft(handball, on: &profile, at: now.addingTimeInterval(Double(i))) }
        XCTAssertFalse(profile.suppresses(category: "handball", now: now.addingTimeInterval(5)))
        XCTAssertEqual(profile.score(for: "handball", now: now.addingTimeInterval(5)), 0)
    }

    // MARK: - Paired controls: what must NOT change

    /// Non-sports feedback still learns — three politics swipes still cool
    /// politics. Fails if the fix is widened to every category.
    func testNonSportsSwipesStillCoolTheirCategory() throws {
        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        for id in 0..<3 {
            swipeLeft(try futures(id, category: "politics"), on: &profile, at: now.addingTimeInterval(Double(id)))
        }
        XCTAssertTrue(profile.suppresses(category: "politics", now: now.addingTimeInterval(3)))
    }

    /// Positive sports signals are untouched: they still raise the score and
    /// still decay like every other score.
    func testSportsLikesStillLearn() throws {
        var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
        let game = try event(1, sport: "americanfootball_nfl")
        swipeRight(game, on: &profile, at: now)
        swipeRight(game, on: &profile, at: now)
        XCTAssertEqual(profile.adjustment(for: "americanfootball", now: now), 4, accuracy: 0.01)
        XCTAssertEqual(
            profile.score(for: "americanfootball",
                          now: now.addingTimeInterval(DiscoverInteractionProfile.cooldownTTL + 1)),
            0)
    }

    // MARK: - Scores saved before the fix

    /// An in-memory legacy penalty reads as neutral — so it can neither cool the
    /// sport down nor eat into a new like.
    func testASavedSportsPenaltyReadsAsNeutral() {
        var profile = DiscoverInteractionProfile.forTesting(
            scores: ["baseball": -9, "politics": -4, "hockey": 6], recordedAt: now)
        XCTAssertEqual(profile.score(for: "baseball", now: now), 0)
        XCTAssertFalse(profile.suppresses(category: "baseball", now: now))
        XCTAssertTrue(profile.suppresses(category: "politics", now: now), "control: non-sports kept")
        XCTAssertEqual(profile.adjustment(for: "hockey", now: now), 6, accuracy: 0.001,
                       "control: a positive sports score kept")

        profile.record(category: "baseball", action: .like, now: now)
        XCTAssertEqual(profile.score(for: "baseball", now: now), 2, accuracy: 0.001,
                       "a new like starts from neutral, not from the retired −9")
    }

    /// The version-2 store on disk: the retired penalty is dropped on load and
    /// stays dropped however many times the profile loads — nothing to run twice.
    func testLoadDropsSavedSportsPenaltiesIdempotently() {
        let at = now.addingTimeInterval(-3600).timeIntervalSince1970
        UserDefaults.standard.set([
            "baseball": ["score": -6.0, "at": at],
            "americanfootball": ["score": -4.0, "at": at],
            "politics": ["score": -4.0, "at": at],
            "hockey": ["score": 5.0, "at": at],
        ], forKey: DiscoverInteractionProfile.storageKey)

        for pass in 1...2 {
            var profile = DiscoverInteractionProfile.load(now: now)
            XCTAssertEqual(profile.score(for: "baseball", now: now), 0, "pass \(pass)")
            XCTAssertEqual(profile.score(for: "americanfootball", now: now), 0, "pass \(pass)")
            XCTAssertTrue(profile.suppresses(category: "politics", now: now), "pass \(pass)")
            XCTAssertGreaterThan(profile.score(for: "hockey", now: now), 4.9, "pass \(pass)")
            // Any write persists the cleaned profile.
            profile.record(category: "entertainment", action: .contextExpand, now: now)
        }
        let raw = UserDefaults.standard.dictionary(forKey: DiscoverInteractionProfile.storageKey)
        XCTAssertNil(raw?["baseball"], "the retired penalty is gone from disk after a save")
        XCTAssertNil(raw?["americanfootball"])
        XCTAssertNotNil(raw?["politics"])
        XCTAssertNotNil(raw?["hockey"])
    }

    /// The version-1 store (no timestamps) migrates without its sports penalties.
    func testLegacyV1MigrationLeavesSportsPenaltiesBehind() {
        UserDefaults.standard.set(
            ["baseball": -5.0, "politics": -4.0, "soccer": 3.0],
            forKey: DiscoverInteractionProfile.legacyStorageKey)

        let profile = DiscoverInteractionProfile.load(now: now)
        XCTAssertEqual(profile.score(for: "baseball", now: now), 0)
        XCTAssertTrue(profile.suppresses(category: "politics", now: now))
        XCTAssertEqual(profile.score(for: "soccer", now: now), 3, accuracy: 0.001)

        let raw = UserDefaults.standard.dictionary(forKey: DiscoverInteractionProfile.storageKey)
        XCTAssertNil(raw?["baseball"])
        XCTAssertNotNil(raw?["politics"])
        XCTAssertNotNil(raw?["soccer"])
        XCTAssertNil(UserDefaults.standard.object(forKey: DiscoverInteractionProfile.legacyStorageKey))
    }

    // MARK: - Presentation: the Red Sox card is not sunk

    /// End to end through the stage `filteredItems` runs: a legacy baseball
    /// penalty no longer sinks a baseball card behind the page, while a legacy
    /// politics penalty still sinks its card (paired arm).
    func testALegacyBaseballPenaltyNoLongerSinksABaseballCard() throws {
        var page: [FeedItem] = [try futures(1, category: "baseball"), try futures(2, category: "politics")]
        for id in 3...14 { page.append(try futures(id, category: "tech")) }
        let profile = DiscoverInteractionProfile.forTesting(
            scores: ["baseball": -9, "politics": -9], recordedAt: now)

        let rendered = DiscoverView.applyCooldownSink(
            to: page,
            isCooled: { profile.suppresses(category: DiscoverCategory.of($0), now: self.now) }
        )
        let ids = rendered.map { DiscoverView.feedItemId($0) }
        XCTAssertEqual(ids.first, DiscoverView.feedItemId(page[0]), "the baseball card keeps its place")
        XCTAssertGreaterThan(
            ids.firstIndex(of: DiscoverView.feedItemId(page[1])) ?? -1, 1,
            "control: the politics card still sinks")
    }

    // MARK: - The classifier

    func testIsSportsFeedbackFollowsTheServerRule() throws {
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(try futures(1, category: "baseball")))
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(try futures(2, category: "Rugby")),
                      "the category is read case-insensitively, as the classifier lowercases it")
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(try futures(3, category: "cycling")),
                      "server-sports even though the interleave keeps cycling out of its partition")
        XCTAssertFalse(DiscoverCategory.isSportsFeedback(try futures(4, category: "politics")))
        XCTAssertFalse(DiscoverCategory.isSportsFeedback(try futures(5, category: "entertainment")))
        XCTAssertFalse(DiscoverCategory.sportsCategories.contains("cycling"),
                       "premise: the interleave set is unchanged by #9648")

        let concept = try decode("""
        { "type": "concept", "score": 90,
          "data": { "key": "ufc:ufc-310", "name": "UFC 310", "domain": "ufc", "status": "live" } }
        """)
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(concept))

        let bundle = try decode("""
        { "type": "bundle", "score": 95,
          "data": { "id": "b1", "title": "Tonight", "kind": "comparison", "comparison_theme": "games",
                    "items": [\(eventJSON(7, sport: "handball_ehf"))] } }
        """)
        XCTAssertTrue(DiscoverCategory.isSportsFeedback(bundle), "a bundle answers for its game child")
    }
}
