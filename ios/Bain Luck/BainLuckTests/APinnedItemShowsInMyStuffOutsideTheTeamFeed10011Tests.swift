import XCTest
@testable import Bain_Luck

/// #10011 — Build 33: Manage pins listed every saved item, but My Stuff drew a
/// pin only when the followed-team feed also carried it, so pinned markets and
/// other sports' games had no content anywhere.
@MainActor
final class APinnedItemShowsInMyStuffOutsideTheTeamFeed10011Tests: XCTestCase {
    private let game = SavedPin(type: "event", value: 501)
    private let market = SavedPin(type: "future", value: 902)
    private let teamGame = SavedPin(type: "event", value: 77)

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func eventDetail(_ id: Int = 501, status: String = "live") throws -> EventDetail {
        try decode(EventDetail.self, #"""
        {"id": \#(id), "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
         "commence_time": "2026-10-04T20:25:00+00:00", "status": "\#(status)",
         "home_score": 14, "away_score": 10,
         "current_odds": {"home_probability": 0.64, "away_probability": 0.36}}
        """#)
    }

    private func marketDetail(winner: Bool = false) throws -> FuturesMarketDetail {
        try decode(FuturesMarketDetail.self, #"""
        {"id": 902, "name": "Who will win the 2026 World Series?", "status": "open",
         "llm_sport_category": "baseball", "outcome_count": 5,
         "outcomes": [
           {"id": 1, "name": "Dodgers", "probability": 0.31},
           {"id": 2, "name": "Yankees", "probability": 0.22, "is_winner": \#(winner)},
           {"id": 3, "name": "Phillies", "probability": 0.18},
           {"id": 4, "name": "Mets", "probability": null},
           {"id": 5, "name": "Brewers", "probability": 0.12}
         ]}
        """#)
    }

    private func feedItem(eventID: Int) throws -> FeedItem {
        try decode(FeedItem.self, #"""
        {"type": "event", "score": 80, "reason": "Your team",
         "data": {"id": \#(eventID), "home_team": "Boston Red Sox", "away_team": "New York Yankees", "status": "scheduled"}}
        """#)
    }

    // MARK: - The section: every pin, not the feed intersection

    func testPinsOutsideTheTeamFeedBecomeCardsInSavedOrder() throws {
        let content: [SavedPin: SavedPinContent] = [
            game: .event(FeedEventData(savedPinDetail: try eventDetail())),
            market: .market(FeedFuturesData(savedPinDetail: try marketDetail())),
        ]
        let section = SavedPinContent.section(pins: [game, market], feed: [], content: content)
        XCTAssertEqual(section.items.map(\.id), ["event-501", "futures-902"])
        XCTAssertEqual(section.items.map(\.type), ["event", "futures"])
        XCTAssertTrue(section.fallbacks.isEmpty)
    }

    /// Strawman: the Build 33 rule (feed ∩ saved IDs) shows nothing for these pins.
    func testControlTheBuild33FeedIntersectionShowsNoneOfThem() throws {
        let feed = [try feedItem(eventID: 77)]
        let intersection = feed.filter { $0.event.map { [501].contains($0.id) } ?? false }
        XCTAssertTrue(intersection.isEmpty)
        let section = SavedPinContent.section(
            pins: [game], feed: feed,
            content: [game: .event(FeedEventData(savedPinDetail: try eventDetail()))])
        XCTAssertEqual(section.items.map(\.id), ["event-501"])
    }

    func testAPinTheFeedAlreadyCarriesKeepsItsFeedCard() throws {
        let feed = [try feedItem(eventID: 77)]
        let section = SavedPinContent.section(pins: [teamGame], feed: feed, content: [:])
        XCTAssertEqual(section.items.map(\.id), ["event-77"])
        XCTAssertEqual(section.items.first?.reason, "Your team")
        XCTAssertTrue(section.fallbacks.isEmpty)
    }

    func testUnloadedGoneAndFailedPinsStayListedAsFallbacks() {
        let gone = SavedPin(type: "event", value: 3)
        let section = SavedPinContent.section(
            pins: [game, market, gone], feed: [],
            content: [market: .failed, gone: .unavailable])
        XCTAssertTrue(section.items.isEmpty)
        XCTAssertEqual(section.fallbacks, [game, market, gone])
        XCTAssertEqual(gone.displayTitle(for: SavedPinContent.unavailable.metadata),
                       "A saved game that's no longer listed")
    }

    func testContentOfTheWrongTypeIsNeverDrawnForAPin() throws {
        let section = SavedPinContent.section(
            pins: [SavedPin(type: "future", value: 501)], feed: [],
            content: [SavedPin(type: "future", value: 501): .event(FeedEventData(savedPinDetail: try eventDetail()))])
        XCTAssertTrue(section.items.isEmpty)
        XCTAssertEqual(section.fallbacks.count, 1)
    }

    // MARK: - The card models

    func testTheGameCardCarriesTheDetailPayloadsStateScoreAndBlend() throws {
        let card = FeedEventData(savedPinDetail: try eventDetail(status: "final"))
        XCTAssertEqual(card.id, 501)
        XCTAssertEqual(card.awayTeam, "Buffalo Bills")
        XCTAssertEqual(card.status, "final")
        XCTAssertEqual(card.homeScore, 14)
        XCTAssertEqual(card.awayScore, 10)
        XCTAssertEqual(card.currentOdds?.homeProbability, 0.64)
    }

    func testTheMarketCardLeadsWithTheHighestPricedOutcomes() throws {
        let card = FeedFuturesData(savedPinDetail: try marketDetail())
        XCTAssertEqual(card.topOutcomes?.map(\.name), ["Dodgers", "Yankees", "Phillies"])
        XCTAssertEqual(card.topOutcomes?.map(\.rank), [1, 2, 3])
        XCTAssertEqual(card.outcomeCount, 5)
        XCTAssertNil(card.winner)
        XCTAssertFalse(FeedLifecycle.futuresIsSettled(card, now: Date(timeIntervalSince1970: 0)))
    }

    func testAGradedMarketLeadsWithItsWinnerAndReadsSettled() throws {
        let card = FeedFuturesData(savedPinDetail: try marketDetail(winner: true))
        XCTAssertEqual(card.topOutcomes?.first?.name, "Yankees")
        XCTAssertEqual(card.winner, "Yankees")
        XCTAssertTrue(FeedLifecycle.futuresIsSettled(card, now: Date(timeIntervalSince1970: 0)))
    }

    // MARK: - Hydration

    private actor Calls {
        var pins: [SavedPin] = []
        func record(_ pin: SavedPin) { pins.append(pin) }
    }

    func testEverySavedPinIsReadWithoutAnyTeamFeed() async throws {
        let calls = Calls()
        let detail = try eventDetail()
        let vm = SavedPinContentViewModel { pin in
            await calls.record(pin)
            return pin.type == "event" ? .event(FeedEventData(savedPinDetail: detail)) : .unavailable
        }
        await vm.load([game, market])
        let read = await calls.pins
        XCTAssertEqual(Set(read), [game, market])
        XCTAssertTrue(vm.content[game]?.hasCard == true)
        XCTAssertEqual(vm.content[market]?.metadata, .unavailable)
    }

    func testARemovedPinDropsItsCardAndAKnownPinIsNotReReadWithoutRefresh() async throws {
        let calls = Calls()
        let detail = try eventDetail()
        let vm = SavedPinContentViewModel { pin in
            await calls.record(pin)
            return .event(FeedEventData(savedPinDetail: detail))
        }
        await vm.load([game, teamGame])
        await vm.load([game])
        XCTAssertNil(vm.content[teamGame])
        let read = await calls.pins
        XCTAssertEqual(read.filter { $0 == game }.count, 1)
    }

    func testRefreshRereadsButAFailedRereadKeepsTheLastCard() async throws {
        let detail = try eventDetail()
        let fail = Flag()
        let vm = SavedPinContentViewModel { _ in
            await fail.value ? .failed : .event(FeedEventData(savedPinDetail: detail))
        }
        await vm.load([game])
        await fail.set(true)
        await vm.load([game], refresh: true)
        XCTAssertTrue(vm.content[game]?.hasCard == true)
    }

    func testRefreshReplacesACardWhoseItemIsGone() async throws {
        let detail = try eventDetail()
        let gone = Flag()
        let vm = SavedPinContentViewModel { _ in
            await gone.value ? .unavailable : .event(FeedEventData(savedPinDetail: detail))
        }
        await vm.load([game])
        await gone.set(true)
        await vm.load([game], refresh: true)
        XCTAssertEqual(vm.content[game]?.metadata, .unavailable)
    }

    func testRetryReadsOnlyFailedPins() async throws {
        let calls = Calls()
        let detail = try eventDetail()
        let first = Flag()
        let market = market
        let vm = SavedPinContentViewModel { pin in
            await calls.record(pin)
            if pin == market, !(await first.value) { return .failed }
            return pin.type == "event" ? .event(FeedEventData(savedPinDetail: detail)) : .unavailable
        }
        await vm.load([game, market])
        XCTAssertEqual(vm.content[market]?.metadata, .failed)
        await first.set(true)
        await vm.load([game, market], retryFailed: true)
        let read = await calls.pins
        XCTAssertEqual(read.filter { $0 == game }.count, 1)
        XCTAssertEqual(read.filter { $0 == market }.count, 2)
        XCTAssertEqual(vm.content[market]?.metadata, .unavailable)
    }

    func testResetClearsTheLastAccountsContent() async throws {
        let detail = try eventDetail()
        let vm = SavedPinContentViewModel { _ in .event(FeedEventData(savedPinDetail: detail)) }
        await vm.load([game])
        vm.reset()
        XCTAssertTrue(vm.content.isEmpty)
    }

    private actor Flag {
        var value = false
        func set(_ v: Bool) { value = v }
    }
}
