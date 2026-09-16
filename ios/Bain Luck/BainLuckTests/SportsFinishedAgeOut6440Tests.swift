import XCTest
@testable import Bain_Luck

/// #6440 — one finished-game age rule, two native feeds.
///
/// `GET /api/feed?mode=sports` deliberately serves finished events the client is
/// expected to delete: `client_deletes_finished_card`
/// (`backend/app/utils/sports_first_page_rails.py`) mirrors web's `isStale` line
/// for line and the first page is composed KNOWING those rows go. Web deletes
/// them in `applyFinishedCardGuard`. The native Sports tab had no age term at
/// all, so on 2026-09-15 22:06Z the phone rendered four finals that
/// bainluck.com/sports did not have in its document — 17.3h to 20.2h old — and
/// native Discover answered the same question a THIRD way: 8h from kickoff, with
/// no marquee exemption.
///
/// These tests pin the one shared predicate (`FeedLifecycle.finishedEventIsExpired`)
/// and both of its consumers. The constants are pinned to web's own file by
/// `frontend/__tests__/lib/finishedCardAgeParity.test.ts`, which reads this
/// runtime's source — a constant in two languages is two constants otherwise.
/// `now` is injected everywhere so no fixture straddles a real boundary (gotcha #44).
@MainActor
final class SportsFinishedAgeOut6440Tests: XCTestCase {

    /// The instant the live measurement in #6440 was taken.
    private let now = ISO8601DateFormatter().date(from: "2026-09-15T23:00:00Z")!

    private func hoursAgo(_ h: Double) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return "\"\(f.string(from: now.addingTimeInterval(-h * 3600)))\""
    }

    private func quoted(_ s: String) -> String { "\"\(s)\"" }

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// One event card, as JSON. `endedAt` / `commenceTime` / `marqueeFinal` are
    /// raw JSON literals so a caller can exercise ABSENCE, which is a different
    /// fact from a value — absent `ended_at` is the pre-D109 payload, absent
    /// `discover_marquee_final` is a surface that does not select marquee finals.
    private func eventJSON(
        id: Int = 100,
        sport: String = "baseball_mlb",
        status: String = "completed",
        endedAt: String = "null",
        commenceTime: String = "null",
        marqueeFinal: String = "null"
    ) -> String {
        """
        {"type":"event","score":80,"data":{"id":\(id),"sport":"\(sport)",
         "home_team":"Home \(id)","away_team":"Away \(id)","status":"\(status)",
         "commence_time":\(commenceTime),"ended_at":\(endedAt),
         "discover_marquee_final":\(marqueeFinal)}}
        """
    }

    private func futuresJSON(id: Int = 7) -> String {
        """
        {"type":"futures","score":88,"data":{"id":\(id),"name":"Who wins \(id)?",
         "llm_sport_category":"baseball","source":"kalshi","status":"open",
         "top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],
         "outcome_count":1}}
        """
    }

    private func item(_ json: String) throws -> FeedItem {
        try Self.decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    private func eventData(_ json: String) throws -> FeedEventData {
        try XCTUnwrap(item(json).event)
    }

    /// The specimen live/303 measured: Diamondbacks–Marlins, `ended_at`
    /// 2026-09-15T04:47:26.482663+00:00, still on the native Sports tab at 22:06Z
    /// while web's document held none of it.
    private func specimenJSON() -> String {
        eventJSON(
            id: 15312206,
            endedAt: quoted("2026-09-15T04:47:26.482663+00:00"),
            commenceTime: quoted("2026-09-15T00:40:00+00:00")
        )
    }

    // MARK: - The predicate

    func testTheProductionSpecimenAgesOut() throws {
        let data = try eventData(specimenJSON())
        // Parsed at all: a six-digit fractional second is what the API actually
        // serves, and an unparsed anchor fails OPEN (the card is kept), so the
        // anchor read is asserted before the verdict that depends on it.
        XCTAssertNotNil(FeedLifecycle.finishedEventAgeAnchor(data))
        XCTAssertTrue(FeedLifecycle.finishedEventIsExpired(data, now: now))
    }

    func testAFreshFinalStays() throws {
        let data = try eventData(eventJSON(endedAt: hoursAgo(2.4)))
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(data, now: now))
    }

    func testTheClockStartsAtTheWhistleNotTheKickoff() throws {
        // A long game: kicked off 9h ago, ended 1h ago. Ageing from kickoff — the
        // rule native Discover used to apply — deleted this card while the result
        // was an hour old.
        let data = try eventData(
            eventJSON(endedAt: hoursAgo(1), commenceTime: hoursAgo(9))
        )
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(data, now: now))
        XCTAssertEqual(
            FeedLifecycle.finishedEventAgeAnchor(data)?.timeIntervalSince1970 ?? 0,
            now.addingTimeInterval(-3600).timeIntervalSince1970,
            accuracy: 1
        )
    }

    func testAnAbsentWhistleFallsBackToKickoff() throws {
        // `ended_at` is OPTIONAL — absent on a cached payload that predates the
        // stamp — and the fallback is the contract, not defensive dressing.
        let data = try eventData(eventJSON(commenceTime: hoursAgo(9)))
        XCTAssertTrue(FeedLifecycle.finishedEventIsExpired(data, now: now))
    }

    func testAnUnreadableAnchorKeepsTheCard() throws {
        let noDates = try eventData(eventJSON())
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(noDates, now: now))
        let garbage = try eventData(
            eventJSON(endedAt: quoted("not a date"), commenceTime: quoted("also not a date"))
        )
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(garbage, now: now))
        // Unknown age has never meant "old" here, and web agrees by arithmetic:
        // `NaN > 8` is false.
    }

    func testAMarqueeFinalGetsTheLongerWindowAndOnlyIt() throws {
        let marqueeAt10 = try eventData(
            eventJSON(endedAt: hoursAgo(10), marqueeFinal: "true")
        )
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(marqueeAt10, now: now))

        let marqueeAt15 = try eventData(
            eventJSON(endedAt: hoursAgo(15), marqueeFinal: "true")
        )
        XCTAssertTrue(FeedLifecycle.finishedEventIsExpired(marqueeAt15, now: now))

        // The flag is scoped: the same age without it is the ordinary window. This
        // is the whole reason D118 added a second constant instead of raising the
        // first one — `/sports` shares the short window with Discover.
        for flag in ["false", "null"] {
            let ordinaryAt10 = try eventData(
                eventJSON(endedAt: hoursAgo(10), marqueeFinal: flag)
            )
            XCTAssertTrue(
                FeedLifecycle.finishedEventIsExpired(ordinaryAt10, now: now),
                "discover_marquee_final=\(flag) must read as the 8h window"
            )
        }
    }

    func testTheWindowsAreTheOnesWebPublishes() {
        XCTAssertEqual(FeedLifecycle.completedEventMaxAgeHours, 8)
        XCTAssertEqual(FeedLifecycle.marqueeFinalMaxAgeHours, 14)
    }

    func testTheComparisonIsStrictSoTheBoundaryRenders() throws {
        let exactly8 = try eventData(eventJSON(endedAt: hoursAgo(8)))
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(exactly8, now: now))
        let aSecondLater = try eventData(eventJSON(endedAt: hoursAgo(8 + 1.0 / 3600)))
        XCTAssertTrue(FeedLifecycle.finishedEventIsExpired(aSecondLater, now: now))
    }

    func testOnlyFinishedStatusesAreEverAged() throws {
        for status in ["scheduled", "live", "suspended", "postponed", ""] {
            let data = try eventData(eventJSON(status: status, endedAt: hoursAgo(48)))
            XCTAssertFalse(
                FeedLifecycle.finishedEventIsExpired(data, now: now),
                "\(status) is not a finished game and must never be aged out"
            )
        }
        // Both finished tokens are, and they are web's pair exactly.
        for status in ["completed", "closed"] {
            let data = try eventData(eventJSON(status: status, endedAt: hoursAgo(48)))
            XCTAssertTrue(FeedLifecycle.finishedEventIsExpired(data, now: now))
        }
    }

    // MARK: - Consumer 1: the Sports tab

    func testTheSportsBucketDropsTheSpecimenAndKeepsTheFreshFinal() throws {
        let items = [
            try item(specimenJSON()),
            try item(eventJSON(id: 2, endedAt: hoursAgo(2.4))),
            try item(eventJSON(id: 3, status: "live")),
        ]
        let kept = FeedViewModel.finishedSection(
            items, now: now,
            reprieved: FeedViewModel.finishedAgeOutIsReprieved(items, now: now)
        )
        XCTAssertEqual(kept.map(\.id), ["event-2"])
    }

    func testAGamelessTabKeepsItsOldFinalsRatherThanEmptying() throws {
        // #1091's reprieve, mirrored from `applyFinishedCardGuard`: when the
        // age-out would leave NO game card at all, the finished ones stay.
        let items = [
            try item(specimenJSON()),
            try item(eventJSON(id: 2, endedAt: hoursAgo(19))),
        ]
        XCTAssertTrue(FeedViewModel.finishedAgeOutIsReprieved(items, now: now))
        let kept = FeedViewModel.finishedSection(
            items, now: now,
            reprieved: FeedViewModel.finishedAgeOutIsReprieved(items, now: now)
        )
        XCTAssertEqual(kept.count, 2)
    }

    func testOneSurvivingGameEndsTheReprieve() throws {
        let survivors = [
            eventJSON(id: 9, status: "live"),
            eventJSON(id: 9, status: "scheduled"),
            eventJSON(id: 9, endedAt: hoursAgo(1)),
        ]
        for survivor in survivors {
            let items = [try item(specimenJSON()), try item(survivor)]
            XCTAssertFalse(
                FeedViewModel.finishedAgeOutIsReprieved(items, now: now),
                "a surviving game card must let the old finals go"
            )
        }
    }

    func testASettledMarketNeverSavesTheOldFinals() throws {
        // Only games count on both sides of the reprieve — a futures card is not
        // what keeps a sports feed from being gameless.
        let items = [try item(specimenJSON()), try item(futuresJSON())]
        XCTAssertTrue(FeedViewModel.finishedAgeOutIsReprieved(items, now: now))
    }

    func testAnEmptyPayloadIsNotReprieved() {
        XCTAssertFalse(FeedViewModel.finishedAgeOutIsReprieved([], now: now))
    }

    /// The bucket the SCREEN reads is the per-category twin, not `justHappened`:
    /// `FeedView`'s "Just Happened" section calls `filteredJustHappened(for:)`. A
    /// gate on the other one would have been inert on the tab that had the bug.
    func testTheRenderedBucketIsGatedAndTheChipCannotResurrectAFinal() async throws {
        let client = StubSportsClient(itemJSONs: [
            specimenJSON(),                                            // MLB, 18.2h
            eventJSON(id: 2, endedAt: hoursAgo(2.4)),                  // MLB, fresh
            eventJSON(id: 3, sport: "americanfootball_nfl", status: "live"),
        ])
        let now = self.now
        let vm = FeedViewModel(
            client: client, telemetry: nil, clock: { now }, autoRefreshEnabled: false
        )
        await vm.load()

        XCTAssertEqual(vm.items.count, 3, "the payload is unchanged; only the bucket filters")
        XCTAssertEqual(vm.filteredJustHappened(for: "all").map(\.id), ["event-2"])
        XCTAssertEqual(vm.justHappened.map(\.id), ["event-2"])
        // The chip slice holds two MLB finals, one of them 18.2h old. The reprieve
        // is asked of the whole payload — where an NFL game is live — so selecting
        // MLB must not bring the old final back.
        XCTAssertEqual(vm.filteredJustHappened(for: "baseball").map(\.id), ["event-2"])
    }

    // MARK: - Consumer 2: Discover

    func testDiscoverReadsTheSameRuleAndNoLongerAgesFromKickoff() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(try item(specimenJSON()), now: now))

        // Was dropped by the old 8h-from-kickoff gate; web keeps it.
        let longGame = try item(eventJSON(endedAt: hoursAgo(1), commenceTime: hoursAgo(9)))
        XCTAssertFalse(DiscoverView.isStaleItem(longGame, now: now))

        // Was dropped at 8h by the old gate, which had no marquee exemption.
        let marquee = try item(eventJSON(endedAt: hoursAgo(10), marqueeFinal: "true"))
        XCTAssertFalse(DiscoverView.isStaleItem(marquee, now: now))
        XCTAssertEqual(DiscoverView.eligibleItems([marquee], now: now).count, 1)
    }

    func testDiscoverStillDropsAnOldFinalThatCarriesOnlyAKickoff() throws {
        // The pre-#6440 fixtures carry no `ended_at`; their behaviour is unchanged.
        let old = try item(eventJSON(commenceTime: hoursAgo(9)))
        XCTAssertTrue(DiscoverView.isStaleItem(old, now: now))
        XCTAssertEqual(DiscoverView.eligibleItems([old], now: now).count, 0)
    }

    // MARK: - Fake

    /// Main feed only; the two optional siblings answer empty so the merge cannot
    /// reintroduce rows this test did not write.
    private nonisolated final class StubSportsClient: SportsFeedProviding, @unchecked Sendable {
        private let itemJSONs: [String]
        init(itemJSONs: [String]) { self.itemJSONs = itemJSONs }

        /// Its own decoder: the suite's is main-actor isolated and this client is
        /// called from the load task, off the actor.
        private func decoder() -> JSONDecoder {
            let dec = JSONDecoder()
            dec.keyDecodingStrategy = .convertFromSnakeCase
            return dec
        }

        private func feed(_ jsons: [String]) throws -> FeedResponse {
            let json = """
            {"items":[\(jsons.joined(separator: ","))],"total":\(jsons.count),
             "limit":50,"offset":0,"has_more":false}
            """
            return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        }

        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            try feed(itemJSONs)
        }

        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            try feed([])
        }

        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            try decoder().decode(
                GroupedFeedResponse.self,
                from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8)
            )
        }
    }
}
