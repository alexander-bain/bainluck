import XCTest
import Combine
@testable import Bain_Luck

/// #10090 — on the iPhone's Discover screen, a card in view moves when the
/// venue moves (display at arrival), the same as web Discover: a live game card
/// adopts the event blend preview (authority-v3, read by the event page's own
/// readers) and a futures card adopts `market_preview` legs. Neither is ever
/// written into the committed card store.
@MainActor
final class DiscoverCardPreview10090Tests: XCTestCase {

    // MARK: - Fixtures

    private func decode<T: Decodable>(_ value: Any, as: T.Type) throws -> T {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private func gameData(rev: Int? = 10, p: Double = 0.5, status: String = "live", hero: String = "blend",
                          sport: String = "basketball_nba", away: Bool = true) -> [String: Any] {
        var odds: [String: Any] = ["home_probability": p, "home_rendered_percent": Int((p * 100).rounded())]
        if away {
            odds["away_probability"] = 1 - p
            odds["away_rendered_percent"] = 100 - Int((p * 100).rounded())
        }
        var data: [String: Any] = ["id": 1, "home_team": "Home", "away_team": "Away", "sport": sport,
                                   "status": status, "hero_probability_source": hero, "current_odds": odds]
        if let rev { data["blend_fold_revision"] = ["1": rev] }
        return data
    }

    private func game(rev: Int? = 10, p: Double = 0.5, status: String = "live", hero: String = "blend",
                      sport: String = "basketball_nba", away: Bool = true) throws -> FeedItem {
        try decode(["type": "event", "score": 90,
                    "data": gameData(rev: rev, p: p, status: status, hero: hero, sport: sport, away: away)],
                   as: FeedItem.self)
    }

    private static let t0 = "2026-11-03T00:00:00Z"

    private func marketData(_ probabilities: [Double] = [0.555, 0.445], scale: Double? = 1,
                            clock: String = t0, source: String = "kalshi") -> [String: Any] {
        let ids = [10, 20, 30]
        var data: [String: Any] = [
            "id": 7, "name": "Market", "source": source, "status": "open", "group_id": "g",
            "canonical_market_key": "k", "outcome_count": probabilities.count,
            "outcome_observed_at": Dictionary(uniqueKeysWithValues: probabilities.indices.map { (String(ids[$0]), clock) }),
            "top_outcomes": probabilities.indices.map { i -> [String: Any] in
                ["id": ids[i], "name": "Leg \(i)", "probability": probabilities[i], "price_observed_at": clock]
            },
        ]
        if let scale { data["display_scale"] = scale }
        return data
    }

    private func market(_ probabilities: [Double] = [0.555, 0.445], scale: Double? = 1,
                        clock: String = t0, source: String = "kalshi") throws -> FeedItem {
        try decode(["type": "futures", "score": 90,
                    "data": marketData(probabilities, scale: scale, clock: clock, source: source)], as: FeedItem.self)
    }

    private static func blendJSON(_ seq: Int, _ p: Double, epoch: Int = 1, base: Int = 10,
                                  ttl: Int = 10_000, status: String = "live") -> String {
        """
        {"event_id":1,"p":\(p),"status":"\(status)","source":"kalshi","source_value":\(p),
         "provisional":true,
         "preview":{"kind":"blend","epoch":\(epoch),"seq":\(seq),"base_rev":\(base),"ttl_ms":\(ttl),
                    "pending":{"kalshi":\(p)}}}
        """
    }

    private static func revokeJSON(_ seq: Int, through: Int, epoch: Int = 1) -> String {
        """
        {"event_id":1,"p":null,"status":"live","provisional":true,
         "preview":{"kind":"revoke","epoch":\(epoch),"seq":\(seq),"through_seq":\(through),"reason":"stale"}}
        """
    }

    private static func marketFrame(_ outcomes: [(Int, Double)], seq: Int = 1_762_128_000_000_001,
                                    observed: String = "2026-11-03T00:00:01.500000+00:00",
                                    ttl: Int = 10_000, market: Int = 7, preview: String = "true") -> String {
        let rows = outcomes.map { #"{"outcome_id":\#($0.0),"p":\#($0.1),"observed_at":"\#(observed)"}"# }
        return """
        {"type":"market_preview","preview":\(preview),"market_id":\(market),"source":"kalshi",\
        "outcomes":[\(rows.joined(separator: ","))],"seq":\(seq),"ttl_ms":\(ttl),\
        "published_at":"2026-11-03T00:00:01.6+00:00"}
        """
    }

    /// A reader opened on the card's membership, as `DiscoverViewModel` opens it.
    private func openedReader(_ card: FeedItem) -> (DiscoverEventPreview, String) {
        let session = V3PageWire.nextSession()
        var view = DiscoverEventPreview()
        _ = view.adoptMembership(of: card.event)
        view.reset() // the transport's `open`
        view.open(V3PageWire.open(1, members: [1], session: session), eventId: 1)
        return (view, session)
    }

    private func dumped(_ value: Any) -> String {
        var text = ""
        dump(value, to: &text)
        return text
    }

    private func printed(_ item: FeedItem) -> [Int?] {
        let odds = item.event?.currentOdds
        return duelPercents(away: odds?.awayProbability, home: odds?.homeProbability,
                            servedAway: odds?.awayRenderedPercent, servedHome: odds?.homeRenderedPercent)
    }

    // MARK: - Game cards (event blend preview)

    func testABlendPreviewMovesAVisibleGameCardsPrintedNumber() throws {
        let card = try game(p: 0.5)
        var (view, session) = openedReader(card)
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session), eventId: 1, now: 100)
        let previews = DiscoverCardPreviews(events: [1: try XCTUnwrap(view.shown)], now: 100)
        let shown = previews.overlay(card)
        XCTAssertEqual(shown.event?.currentOdds?.homeProbability, 0.7)
        XCTAssertEqual(try XCTUnwrap(shown.event?.currentOdds?.awayProbability), 0.3, accuracy: 1e-9)
        XCTAssertNil(shown.event?.currentOdds?.homeRenderedPercent, "the served whole percents describe the committed pair")
        XCTAssertEqual(printed(shown), [30, 70])
        XCTAssertEqual(printed(card), [50, 50], "the committed card itself is untouched")
    }

    func testADrawPricedCardKeepsItsWithheldAwaySide() throws {
        let card = try game(p: 0.5, sport: "soccer_epl", away: false)
        var (view, session) = openedReader(card)
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.62), eventId: 1, session: session), eventId: 1, now: 100)
        let shown = DiscoverCardPreviews(events: [1: try XCTUnwrap(view.shown)], now: 100).overlay(card)
        XCTAssertEqual(shown.event?.currentOdds?.homeProbability, 0.62)
        XCTAssertNil(shown.event?.currentOdds?.awayProbability)
    }

    func testANewerCommittedRevisionReplacesItAndAnOlderOrEqualOneDoesNot() throws {
        var (view, session) = openedReader(try game(rev: 10))
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session), eventId: 1, now: 100)
        let previews = DiscoverCardPreviews(events: [1: try XCTUnwrap(view.shown)], now: 101)
        XCTAssertEqual(previews.overlay(try game(rev: 11, p: 0.55)).event?.currentOdds?.homeProbability, 0.55,
                       "a committed read past the preview's base wins")
        XCTAssertEqual(previews.overlay(try game(rev: 10, p: 0.55)).event?.currentOdds?.homeProbability, 0.7)
        XCTAssertEqual(previews.overlay(try game(rev: 9, p: 0.55)).event?.currentOdds?.homeProbability, 0.7)
    }

    func testRevokeTTLLowerEpochAndLowerSeqAreRefused() throws {
        let card = try game()
        func shown(_ view: DiscoverEventPreview, at now: TimeInterval) -> Double? {
            guard let state = view.shown else { return nil }
            return DiscoverCardPreviews(events: [1: state], now: now).overlay(card).event?.currentOdds?.homeProbability
        }
        var (view, session) = openedReader(card)
        func send(_ frame: String, at now: TimeInterval = 100) {
            view.preview(V3PageWire.preview(frame, eventId: 1, session: session), eventId: 1, now: now)
        }
        send(Self.blendJSON(5, 0.7, epoch: 2))
        XCTAssertEqual(shown(view, at: 100), 0.7)
        send(Self.blendJSON(4, 0.6, epoch: 2))
        XCTAssertEqual(shown(view, at: 100), 0.7, "a lower seq never replaces a higher one")
        send(Self.blendJSON(9, 0.6, epoch: 1))
        XCTAssertEqual(shown(view, at: 100), 0.7, "a lower epoch is fenced out")
        XCTAssertEqual(shown(view, at: 110), 0.5, "past its ttl the committed number shows")
        send(Self.revokeJSON(6, through: 5, epoch: 2))
        XCTAssertNil(view.shown, "a revoke through its seq withdraws it")
        XCTAssertEqual(shown(view, at: 100), nil)
    }

    func testANonBlendHeroIgnoresPreviews() throws {
        let card = try game(hero: "consensus")
        var (view, session) = openedReader(card)
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session), eventId: 1, now: 100)
        XCTAssertNil(view.shown, "no blend revision: no membership, so the v3 open is never admitted")
        // Even a held state never prints over a hero that is not the blend.
        var blend = openedReader(try game())
        blend.0.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: blend.1), eventId: 1, now: 100)
        let previews = DiscoverCardPreviews(events: [1: try XCTUnwrap(blend.0.shown)], now: 100)
        XCTAssertEqual(dumped(previews.overlay(card)), dumped(card))
    }

    func testAReconnectOrAnOutOfViewCardClearsTheGamePreview() throws {
        var (view, session) = openedReader(try game())
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session), eventId: 1, now: 100)
        XCTAssertNotNil(view.shown)
        view.reset()
        XCTAssertNil(view.shown, "a connection boundary withdraws the display")
        // The old session's frames are refused until a new open names one.
        view.preview(V3PageWire.preview(Self.blendJSON(2, 0.71), eventId: 1, session: session), eventId: 1, now: 100)
        XCTAssertNil(view.shown)
    }

    // MARK: - Futures cards (market_preview)

    func testAMarketPreviewMovesAFuturesCardLeg() throws {
        let card = try market([0.40, 0.30, 0.20])
        let frame = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)])))
        let states = DiscoverMarketPreview.apply([:], frame, receivedAt: 100)
        let shown = DiscoverCardPreviews(markets: states, now: 100).overlay(card)
        XCTAssertEqual(shown.futures?.topOutcomes?.map(\.probability), [0.40, 0.35, 0.20])
        XCTAssertEqual(card.futures?.topOutcomes?.map(\.probability), [0.40, 0.30, 0.20])
        XCTAssertEqual(DiscoverCardPreviews(markets: states, now: 110).overlay(card).futures?.topOutcomes?.map(\.probability),
                       [0.40, 0.30, 0.20], "past its ttl the committed leg shows")
    }

    func testAnEqualOrNewerCommittedObservationReplacesTheLeg() throws {
        let frame = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)])))
        let states = DiscoverMarketPreview.apply([:], frame, receivedAt: 100)
        let previews = DiscoverCardPreviews(markets: states, now: 100)
        for clock in ["2026-11-03T00:00:01.5Z", "2026-11-03T00:00:02Z"] {
            let card = try market([0.40, 0.30, 0.20], clock: clock)
            XCTAssertEqual(previews.overlay(card).futures?.topOutcomes?.map(\.probability), [0.40, 0.30, 0.20], clock)
        }
        XCTAssertEqual(previews.overlay(try market([0.40, 0.30, 0.20], clock: "2026-11-03T00:00:01.499999Z"))
            .futures?.topOutcomes?.map(\.probability), [0.40, 0.35, 0.20], "an older committed leg is beaten")
    }

    func testADisplayScaleOtherThanOneIsIgnored() throws {
        let frame = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)])))
        let previews = DiscoverCardPreviews(markets: DiscoverMarketPreview.apply([:], frame, receivedAt: 100), now: 100)
        for scale: Double? in [1.05, nil] {
            let card = try market([0.40, 0.30, 0.20], scale: scale)
            XCTAssertEqual(dumped(previews.overlay(card)), dumped(card), "scale \(String(describing: scale))")
        }
        let otherSource = try market([0.40, 0.30, 0.20], source: "polymarket")
        XCTAssertEqual(dumped(previews.overlay(otherSource)), dumped(otherSource))
    }

    func testAComplementPairPrintsOneHundredOnAOneSidedMove() throws {
        let card = try market([0.555, 0.445])
        let frame = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.425)])))
        let shown = DiscoverCardPreviews(markets: DiscoverMarketPreview.apply([:], frame, receivedAt: 100), now: 100)
            .overlay(card)
        let probabilities = try XCTUnwrap(shown.futures?.topOutcomes?.map(\.probability))
        XCTAssertEqual(probabilities, [0.575, 0.425])
        let percents = renderedCardPercents(probabilities).compactMap { $0 }
        XCTAssertEqual(percents, [58, 42])
        XCTAssertEqual(percents.reduce(0, +), 100)
        // Without the complement, the card would print 56 / 43 = 99.
        XCTAssertEqual(renderedCardPercents([0.555, 0.425]).compactMap { $0 }.reduce(0, +), 99)
        // Two previewed legs that are not a pair keep the committed pair.
        let both = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(10, 0.6), (20, 0.425)])))
        let kept = DiscoverCardPreviews(markets: DiscoverMarketPreview.apply([:], both, receivedAt: 100), now: 100)
            .overlay(card)
        XCTAssertEqual(kept.futures?.topOutcomes?.map(\.probability), [0.555, 0.445])
    }

    func testSeqIsFencedPerMarketAndMalformedFramesAreRefused() throws {
        let first = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)], seq: 5)))
        let states = DiscoverMarketPreview.apply([:], first, receivedAt: 100)
        for seq in [5, 4] {
            let stale = try XCTUnwrap(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.31)], seq: seq)))
            XCTAssertEqual(DiscoverMarketPreview.apply(states, stale, receivedAt: 101), states, "seq \(seq)")
        }
        XCTAssertNil(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)], preview: "1")))
        XCTAssertNil(DiscoverMarketPreview.parse(Self.marketFrame([(20, 1.0)])), "a terminal price is settlement's")
        XCTAssertNil(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)], ttl: 60_001)))
        XCTAssertNil(DiscoverMarketPreview.parse(Self.marketFrame([(20, 0.35)], observed: "soon")))
        XCTAssertNil(DiscoverMarketPreview.parse("{\"type\":\"market\",\"market_id\":7}"))
    }

    // MARK: - Control

    func testNoPreviewsLeaveEveryCardByteIdentical() throws {
        let cards = [try game(), try market(), try market([0.40, 0.30, 0.20])]
        XCTAssertEqual(dumped(DiscoverCardPreviews().overlay(cards)), dumped(cards))
        // Another card's preview changes nothing on these.
        var (view, session) = openedReader(try game())
        view.preview(V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session), eventId: 1, now: 100)
        let elsewhere = DiscoverCardPreviews(
            events: [2: try XCTUnwrap(view.shown)],
            markets: [8: DiscoverMarketPreviewState(source: "kalshi", seq: 1,
                                                    legs: ["20": .init(p: 0.3, observedAt: "2026-11-03T00:00:05Z", expiresAt: 200)])],
            now: 100)
        XCTAssertEqual(dumped(elsewhere.overlay(cards)), dumped(cards))
    }

    // MARK: - Market stream subscription

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for handler in handlers[event] ?? [] { handler(data) }
        }
    }

    func testTheMarketStreamForwardsPreviewsAndResetsThemAtEveryConnectionEnd() {
        var handles: [Handle] = []
        var frames: [DiscoverMarketPreviewFrame] = []
        var resets: [[Int]] = []
        var invalidations = 0
        let subscription = MarketStreamSubscription(
            makeHandle: { _ in let handle = Handle(); handles.append(handle); return handle },
            onInvalidate: { _ in invalidations += 1 },
            onPreview: { frames.append($0) }, onPreviewReset: { resets.append($0) },
            now: { 0 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        subscription.start(ids: [7, 8])
        handles[0].fire("market_preview", Self.marketFrame([(20, 0.35)]))
        handles[0].fire("market_preview", Self.marketFrame([(20, 0.35)], market: 9))
        XCTAssertEqual(frames.map(\.marketId), [7], "only this connection's markets")
        XCTAssertEqual(invalidations, 0, "a preview is never an invalidation")
        handles[0].fire("error")
        XCTAssertEqual(resets, [[7, 8]])
        handles[0].fire("reconnect")
        XCTAssertEqual(resets.last, [7, 8])
        handles[0].fire("market_preview", Self.marketFrame([(20, 0.36)], seq: 1_762_128_000_000_002))
        XCTAssertEqual(frames.count, 1, "a retired connection forwards nothing")
        subscription.stop()
        XCTAssertEqual(resets.count, 2, "stop after a recycle has nothing left to reset")
    }

    // MARK: - View model: streams open and close with the cards in view

    private nonisolated final class Client: DiscoverFeedProviding, DiscoverPriceCardsProviding, @unchecked Sendable {
        let feed: FeedResponse
        let cards: DiscoverPriceCards
        init(feed: FeedResponse, cards: DiscoverPriceCards) { self.feed = feed; self.cards = cards }
        func fetchDiscoverFeed(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> FeedResponse { feed }
        func fetchDiscoverPriceCards(eventIds: [Int], marketIds: [Int]) async throws -> DiscoverPriceCards { cards }
    }

    private func model(_ data: [String: Any], type: String, clock: @escaping () -> TimeInterval,
                       eventHandle: Handle? = nil, marketHandle: Handle? = nil) async throws -> (DiscoverViewModel, FeedItem) {
        let feed = try decode(["items": [["type": type, "score": 90, "data": data]], "total": 1, "limit": 50,
                               "offset": 0, "has_more": false, "edition": "e"], as: FeedResponse.self)
        let card = try XCTUnwrap(feed.items.first)
        let client = Client(feed: feed, cards: DiscoverPriceCards(items: [], dispositions: [:], builtAt: 100))
        var marketFactory: MarketStreamSubscription.Factory?
        if let marketHandle { marketFactory = { _ in marketHandle } }
        var eventFactory: (@MainActor (Int) throws -> LiveStreamHandle)?
        if let eventHandle { eventFactory = { _ in eventHandle } }
        let vm = DiscoverViewModel(client: client, priceClient: client,
                                   makePriceMarketHandle: marketFactory, makePriceEventHandle: eventFactory,
                                   previewNow: clock, lastGood: nil, telemetry: nil)
        await vm.load()
        return (vm, try XCTUnwrap(vm.items.first))
    }

    func testAVisibleGameCardMovesAtArrivalAndClearsWhenItLeavesView() async throws {
        var clock: TimeInterval = 100
        let handle = Handle()
        let (vm, card) = try await model(gameData(), type: "event", clock: { clock }, eventHandle: handle)
        let committed = dumped(vm.items)
        vm.setPriceDeliveryActive(true)
        XCTAssertEqual(dumped(vm.previewed(card)), dumped(card), "control: an open stream with no preview changes nothing")
        vm.setPriceCardsVisible(owner: card.id, cards: [card], visible: true)
        handle.fire("open")
        let session = V3PageWire.nextSession()
        handle.fire("preview_open_v3", V3PageWire.open(1, members: [1], session: session))
        handle.fire("preview_v3", V3PageWire.preview(Self.blendJSON(1, 0.7), eventId: 1, session: session))
        XCTAssertEqual(vm.previewed(card).event?.currentOdds?.homeProbability, 0.7)
        XCTAssertEqual(dumped(vm.items), committed, "a preview is never written into the committed store")
        clock = 111
        XCTAssertEqual(vm.cardPreviews.overlay(card).event?.currentOdds?.homeProbability, 0.7,
                       "judged at the published time until the expiry re-render")
        vm.setPriceCardsVisible(owner: card.id, cards: [], visible: false)
        XCTAssertTrue(handle.isClosed)
        XCTAssertTrue(vm.cardPreviews.isEmpty, "out of view drops the reader and its preview")
        XCTAssertEqual(dumped(vm.previewed(card)), dumped(card))
        vm.setPriceDeliveryActive(false)
    }

    func testAVisibleFuturesCardMovesAtArrivalAndAReconnectClearsIt() async throws {
        let handle = Handle()
        let (vm, card) = try await model(marketData([0.40, 0.30, 0.20]), type: "futures", clock: { 100 },
                                         marketHandle: handle)
        vm.setPriceDeliveryActive(true)
        vm.setPriceCardsVisible(owner: card.id, cards: [card], visible: true)
        handle.fire("market_preview", Self.marketFrame([(20, 0.35)]))
        XCTAssertEqual(vm.previewed(card).futures?.topOutcomes?.map(\.probability), [0.40, 0.35, 0.20])
        XCTAssertEqual(vm.items.first?.futures?.topOutcomes?.map(\.probability), [0.40, 0.30, 0.20])
        handle.fire("reconnect")
        XCTAssertTrue(vm.cardPreviews.isEmpty)
        XCTAssertEqual(vm.previewed(card).futures?.topOutcomes?.map(\.probability), [0.40, 0.30, 0.20])
        vm.setPriceDeliveryActive(false)
    }

    func testBackgroundingClearsEveryPreview() async throws {
        let handle = Handle()
        let (vm, card) = try await model(marketData([0.40, 0.30, 0.20]), type: "futures", clock: { 100 },
                                         marketHandle: handle)
        vm.setPriceDeliveryActive(true)
        vm.setPriceCardsVisible(owner: card.id, cards: [card], visible: true)
        handle.fire("market_preview", Self.marketFrame([(20, 0.35)]))
        XCTAssertFalse(vm.cardPreviews.isEmpty)
        vm.setPriceDeliveryActive(false)
        XCTAssertTrue(handle.isClosed)
        XCTAssertTrue(vm.cardPreviews.isEmpty)
    }
}
