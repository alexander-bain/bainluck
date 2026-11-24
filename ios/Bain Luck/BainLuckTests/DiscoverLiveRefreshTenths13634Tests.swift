import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// `#13634` + Direction 395 (`#12538`) — Live game cards on Discover refresh
/// chances and scores on the Sports tab's timer (`30 s`) and print **whole
/// percents** (`54%`) across every timer-refreshed and non-refreshing surface in
/// 1.0.8 (Discover, Sports tab, My Stuff, Search, Team, League, Sport, Hub).
/// `liveOddsRefreshActive` / `showsLiveTenths` plumbing remains default `false`
/// (nothing sets it `true` in 1.0.8) so 1.0.9 can turn tenths on for sub-second
/// per-card streams. The game detail page is unchanged.
@MainActor
final class DiscoverLiveRefreshTenths13634Tests: XCTestCase {

    // MARK: - Helpers & Scripted Fakes

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ value: Any) throws -> T {
        let data: Data
        if let str = value as? String {
            data = Data(str.utf8)
        } else {
            data = try JSONSerialization.data(withJSONObject: value)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }

    private func makeLiveEventDict(
        id: Int = 15353579,
        sport: String = "basketball_ncaab",
        sportName: String = "Men's CBB",
        awayTeam: String = "Ole Miss Rebels",
        homeTeam: String = "BYU Cougars",
        awayScore: Int = 14,
        homeScore: Int = 20,
        homeProbability: Double = 0.6357,
        awayProbability: Double = 0.3643,
        pregameHomeProbability: Double = 0.54,
        pregameAwayProbability: Double = 0.46,
        foldRevision: Int = 1407,
        priceObservedAt: String = "2026-11-24T19:52:00Z",
        scoreObservedAt: String = "2026-11-24T19:51:50Z",
        withSourceMark: Bool = true
    ) -> [String: Any] {
        let awayRendered = Int((awayProbability * 100).rounded())
        let homeRendered = 100 - awayRendered
        var data: [String: Any] = [
            "id": id,
            "sport": sport,
            "sport_name": sportName,
            "away_team": awayTeam,
            "home_team": homeTeam,
            "away_team_data": ["abbreviation": "MISS", "primary_color": "#CE1126", "secondary_color": "#14213D"],
            "home_team_data": ["abbreviation": "BYU", "primary_color": "#002E5D", "secondary_color": "#FFFFFF"],
            "commence_time": "2026-11-24T19:30:00Z",
            "status": "live",
            "away_score": awayScore,
            "home_score": homeScore,
            "score_source": "espn",
            "score_observed_at": scoreObservedAt,
            "espn": ["period": "1H", "game_clock": "6:42"],
            "blend_fold_revision": [String(id): foldRevision],
            "hero_probability_source": "blend",
            "hero_probability_observed_at": priceObservedAt,
            "prematch_odds": [
                "away_probability": pregameAwayProbability,
                "home_probability": pregameHomeProbability,
                "away_rendered_percent": Int((pregameAwayProbability * 100).rounded()),
                "home_rendered_percent": Int((pregameHomeProbability * 100).rounded()),
                "source": "kalshi"
            ],
            "current_odds": [
                "away_probability": awayProbability,
                "home_probability": homeProbability,
                "away_rendered_percent": awayRendered,
                "home_rendered_percent": homeRendered,
                "projected_away_score": 76.2,
                "projected_home_score": 81.4,
                "live_projection": [
                    "projected_away_score": 76.2,
                    "projected_home_score": 81.4,
                    "kind": "in_play",
                    "boundary": "commence_time",
                    "boundary_at": "2026-11-24T19:30:00Z",
                    "earliest_confirmed_at": priceObservedAt,
                    "latest_captured_at": priceObservedAt,
                    "source": "sportsbooks",
                    "basis": "consensus_spread_total",
                    "bookmaker_count": 12,
                    "unit": "points",
                    "period": "full_game"
                ]
            ]
        ]
        if withSourceMark {
            data["source_mark"] = [
                "state": "blend",
                "sources": [
                    ["key": "sportsbooks", "name": "Sportsbooks", "count": 12, "probability": homeProbability, "observed_at": priceObservedAt],
                    ["key": "kalshi", "name": "Kalshi", "probability": max(0.02, homeProbability - 0.008), "observed_at": priceObservedAt]
                ],
                "method": "Bain Luck blend · weighted average before rounding"
            ]
        }
        return ["type": "event", "score": 95, "data": data]
    }

    private func makeFeedResponse(itemDicts: [[String: Any]]) throws -> FeedResponse {
        try decodeSnake(FeedResponse.self, [
            "items": itemDicts,
            "total": itemDicts.count,
            "limit": 20,
            "offset": 0,
            "has_more": false,
            "edition": "e1"
        ])
    }

    private func makeLastGood(itemDicts: [[String: Any]]) throws -> DiscoverLastGoodReading {
        FixedLastGoodReading(response: try makeFeedResponse(itemDicts: itemDicts))
    }

    private struct FixedLastGoodReading: DiscoverLastGoodReading {
        let response: FeedResponse
        func loadLastGoodFeed() async -> CachedDiscoverFeed? {
            CachedDiscoverFeed(
                response: response,
                storedAt: Date().addingTimeInterval(-45),
                ttlSeconds: 30,
                identity: ""
            )
        }
    }

    private nonisolated final class ScriptedDiscoverClient: DiscoverFeedProviding, DiscoverPriceCardsProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var feedResult: Result<FeedResponse, Error>
        private var priceReplies: [Result<DiscoverPriceCards, Error>]
        private var priceIndex = 0
        private var _priceCallCount = 0

        init(feedResult: Result<FeedResponse, Error>, priceReplies: [Result<DiscoverPriceCards, Error>]) {
            self.feedResult = feedResult
            self.priceReplies = priceReplies
        }

        var priceCallCount: Int { lock.withLock { _priceCallCount } }

        func setFeedResult(_ next: Result<FeedResponse, Error>) {
            lock.withLock { feedResult = next }
        }

        func setPriceReplies(_ next: [Result<DiscoverPriceCards, Error>]) {
            lock.withLock {
                priceReplies = next
                priceIndex = 0
            }
        }

        func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            try lock.withLock { try feedResult.get() }
        }

        func fetchDiscoverPriceCards(eventIds: [Int], marketIds: [Int]) async throws -> DiscoverPriceCards {
            let reply: Result<DiscoverPriceCards, Error> = lock.withLock {
                _priceCallCount += 1
                let idx = min(priceIndex, max(0, priceReplies.count - 1))
                if priceIndex < priceReplies.count - 1 {
                    priceIndex += 1
                }
                return priceReplies[idx]
            }
            return try reply.get()
        }
    }

    private nonisolated final class FailingSportsClient: SportsFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        private let lock = NSLock()
        private var shouldFail = false

        init(feed: FeedResponse) { self.feed = feed }
        func setFail(_ value: Bool) { lock.withLock { shouldFail = value } }

        func fetchSportsFeed() async throws -> FeedResponse {
            if lock.withLock({ shouldFail }) { throw URLError(.notConnectedToInternet) }
            return feed
        }
        func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            let data = Data("{\"items\":[],\"total\":0,\"limit\":\(limit),\"offset\":0,\"has_more\":false}".utf8)
            let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(FeedResponse.self, from: data)
        }
        func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(GroupedFeedResponse.self, from: Data("{\"groups\":[]}".utf8))
        }
    }

    private nonisolated final class FailingMyStuffClient: MyStuffFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        private let lock = NSLock()
        private var shouldFail = false

        init(feed: FeedResponse) { self.feed = feed }
        func setFail(_ value: Bool) { lock.withLock { shouldFail = value } }

        func fetchMyTeamsFeed() async throws -> FeedResponse {
            if lock.withLock({ shouldFail }) { throw URLError(.notConnectedToInternet) }
            return feed
        }
        func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            TeamFuturesResponse(items: [], teamIds: [], totalCount: 0)
        }
    }

    private func waitUntil(
        timeout: TimeInterval = 5.0,
        _ predicate: @escaping @MainActor () -> Bool
    ) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if predicate() { return true }
            try? await Task.sleep(nanoseconds: 20_000_000)
        }
        return predicate()
    }

    private func renderAt390<V: View>(_ view: V, scheme: ColorScheme = .light) -> UIImage {
        let width: CGFloat = 390
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let sized = view
            .frame(width: width, alignment: .topLeading)
            .fixedSize(horizontal: false, vertical: true)
            .background(bg)
            .environment(\.colorScheme, scheme)

        let measureHost = hostForMeasurement(sized, at: .large)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, 220), 2_400)

        let host = hostForMeasurement(sized, at: .large)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) }
            ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<3 {
            let nextH = min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, fittingH), 2_400)
            if abs(nextH - window.frame.height) > 0.5 {
                window.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                host.view.frame = window.bounds
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: host.view.bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrStrings(_ image: UIImage) throws -> [String] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    // MARK: - 1. Discover Live Refresh Pace (30s == Sports Tab) + In-Place Score & Odds Update

    func testDiscoverRefreshPaceMatchesSportsTabAndUpdatesChancesAndScoreInPlace() async throws {
        XCTAssertEqual(
            DiscoverViewModel.liveRefreshInterval,
            FeedViewModel.autoRefreshInterval,
            "Discover live refresh pace must match the Sports tab (30s)"
        )

        let d0 = makeLiveEventDict(
            awayScore: 14,
            homeScore: 20,
            homeProbability: 0.6357,
            awayProbability: 0.3643,
            foldRevision: 1407,
            priceObservedAt: "2026-11-24T19:52:00Z",
            scoreObservedAt: "2026-11-24T19:51:50Z"
        )
        let d1 = makeLiveEventDict(
            awayScore: 14,
            homeScore: 24,
            homeProbability: 0.6761,
            awayProbability: 0.3239,
            foldRevision: 1416,
            priceObservedAt: "2026-11-24T19:52:30Z",
            scoreObservedAt: "2026-11-24T19:52:25Z"
        )
        let d2 = makeLiveEventDict(
            awayScore: 17,
            homeScore: 27,
            homeProbability: 0.7124,
            awayProbability: 0.2876,
            foldRevision: 1425,
            priceObservedAt: "2026-11-24T19:53:00Z",
            scoreObservedAt: "2026-11-24T19:52:55Z"
        )
        let item0 = try decodeSnake(FeedItem.self, d0)
        let item1 = try decodeSnake(FeedItem.self, d1)
        let item2 = try decodeSnake(FeedItem.self, d2)

        let client = ScriptedDiscoverClient(
            feedResult: .success(try makeFeedResponse(itemDicts: [d0])),
            priceReplies: [
                .success(DiscoverPriceCards(items: [item0], dispositions: [item0.id: "updated"], builtAt: 100)),
                .success(DiscoverPriceCards(items: [item1], dispositions: [item0.id: "updated"], builtAt: 101)),
                .success(DiscoverPriceCards(items: [item2], dispositions: [item0.id: "updated"], builtAt: 102)),
            ]
        )

        let vm = DiscoverViewModel(
            client: client,
            priceClient: client,
            lastGood: nil,
            telemetry: nil,
            priceTickInterval: 0.03,
            liveRefreshInterval: 0.06,
            monitorNetworkPath: false
        )
        // Cold-start ordering: view appears BEFORE async feed load finishes.
        vm.setPriceDeliveryActive(true)
        await vm.load()
        vm.setPriceCardsVisible(owner: item0.id, cards: [item0], visible: true)

        let reachedStep2 = await waitUntil(timeout: 6.0) {
            vm.items.first?.event?.currentOdds?.homeProbability == 0.7124
                && vm.items.first?.event?.homeScore == 27
                && vm.items.first?.event?.awayScore == 17
        }
        XCTAssertTrue(reachedStep2, "Periodic Discover refresh must advance both probability and score in place")
        XCTAssertTrue(vm.livePriceRefreshRunning)
        XCTAssertGreaterThanOrEqual(client.priceCallCount, 3)

        let updatedEvent = try XCTUnwrap(vm.items.first?.event)
        let prematch2 = PrematchReading.resolve(prematch: item2.event?.prematchOdds, opening: nil)
        let liveModel = DiscoverSingleGameCard190C.build(
            event: updatedEvent,
            prematch: prematch2,
            usesPictureLayout: true
        )
        XCTAssertEqual(liveModel.rows.map(\.primaryCell), [.probability("29%"), .probability("71%")])
        XCTAssertEqual(liveModel.rows.map(\.scoreText), ["17", "27"])

        let chartModel = DiscoverPictureChart191A.build(
            event: updatedEvent,
            prematch: prematch2,
            history: nil
        )
        XCTAssertFalse(
            chartModel.rightEndLabel.contains("."),
            "Direction 395: Discover picture chart 'Now' label must print whole percents/points, got: \(chartModel.rightEndLabel)"
        )
        let markModel = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: updatedEvent,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: prematch2,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertFalse(markModel.showsTenths, "Direction 395: 'Where this number comes from' sheet must print whole percents on timer-refreshed Discover cards")

        vm.setPriceDeliveryActive(false)
        XCTAssertFalse(vm.livePriceRefreshRunning)
    }

    // MARK: - 2. Network Off / Stopped / Cached States Keep Whole Percents & Resume Refresh

    func testNetworkOffFlipsDiscoverLiveCardToWholePercentsAndRecoversWhenBackOnline() async throws {
        let d0 = makeLiveEventDict(
            awayScore: 14,
            homeScore: 20,
            homeProbability: 0.6357,
            awayProbability: 0.3643,
            foldRevision: 1407,
            priceObservedAt: "2026-11-24T19:52:00Z",
            scoreObservedAt: "2026-11-24T19:51:50Z"
        )
        let item0 = try decodeSnake(FeedItem.self, d0)
        let client = ScriptedDiscoverClient(
            feedResult: .success(try makeFeedResponse(itemDicts: [d0])),
            priceReplies: [.success(DiscoverPriceCards(items: [item0], dispositions: [item0.id: "updated"], builtAt: 100))]
        )

        let vm = DiscoverViewModel(
            client: client,
            priceClient: client,
            lastGood: nil,
            telemetry: nil,
            priceTickInterval: 0.03,
            liveRefreshInterval: 0.06,
            monitorNetworkPath: false
        )
        await vm.load()
        vm.setPriceDeliveryActive(true)
        vm.setPriceCardsVisible(owner: item0.id, cards: [item0], visible: true)

        let onlineReady = await waitUntil { vm.livePriceRefreshRunning && client.priceCallCount >= 1 }
        XCTAssertTrue(onlineReady)

        // Simulate network loss on refresh.
        client.setPriceReplies([.failure(URLError(.notConnectedToInternet))])
        let droppedOffline = await waitUntil(timeout: 3.0) { !vm.livePriceRefreshRunning }
        XCTAssertTrue(droppedOffline, "Failed refresh (network off) must stop livePriceRefreshRunning immediately")

        let event = try XCTUnwrap(vm.items.first?.event)
        let prematch = PrematchReading.resolve(prematch: event.prematchOdds, opening: nil)
        let offlineCard = DiscoverSingleGameCard190C.build(
            event: event,
            prematch: prematch,
            usesPictureLayout: true
        )
        XCTAssertEqual(
            offlineCard.rows.map(\.primaryCell),
            [.probability("36%"), .probability("64%")],
            "When refresh is not running, live Discover card must print whole percents"
        )
        let offlineChart = DiscoverPictureChart191A.build(
            event: event,
            prematch: prematch,
            history: nil
        )
        XCTAssertFalse(
            offlineChart.rightEndLabel.contains("."),
            "Offline chart footer must also print whole percents/points, got: \(offlineChart.rightEndLabel)"
        )
        let offlineMark = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: event,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: prematch,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertFalse(offlineMark.showsTenths)

        // Cached content shown behind a failed feed load keeps refresh inactive.
        client.setFeedResult(.failure(URLError(.notConnectedToInternet)))
        let cachedVM = DiscoverViewModel(
            client: client,
            priceClient: nil,
            lastGood: try makeLastGood(itemDicts: [d0]),
            telemetry: nil,
            retryBudget: 0.05,
            seededRetryBudget: 0.05,
            retryBackoff: 0.01,
            autoRecoveryDelays: [],
            monitorNetworkPath: false
        )
        cachedVM.setPriceDeliveryActive(true)
        await cachedVM.load()
        XCTAssertTrue(cachedVM.isShowingCachedContent)
        XCTAssertTrue(cachedVM.refreshFailedShowingCache)
        XCTAssertFalse(cachedVM.livePriceRefreshRunning)

        // Restore network on primary VM -> recovers automatically and moves whole percents + score.
        let d1 = makeLiveEventDict(
            awayScore: 16,
            homeScore: 26,
            homeProbability: 0.6842,
            awayProbability: 0.3158,
            foldRevision: 1418,
            priceObservedAt: "2026-11-24T19:53:20Z",
            scoreObservedAt: "2026-11-24T19:53:15Z"
        )
        let item1 = try decodeSnake(FeedItem.self, d1)
        client.setPriceReplies([
            .success(DiscoverPriceCards(items: [item1], dispositions: [item0.id: "updated"], builtAt: 103))
        ])
        let recovered = await waitUntil(timeout: 3.0) {
            vm.livePriceRefreshRunning && vm.items.first?.event?.currentOdds?.homeProbability == 0.6842
        }
        XCTAssertTrue(recovered, "Coming back online must resume refresh and move live odds/score")
        let resumedEvent = try XCTUnwrap(vm.items.first?.event)
        let resumedCard = DiscoverSingleGameCard190C.build(
            event: resumedEvent,
            prematch: prematch,
            usesPictureLayout: true
        )
        XCTAssertEqual(resumedCard.rows.map(\.primaryCell), [.probability("32%"), .probability("68%")])
        XCTAssertEqual(resumedCard.rows.map(\.scoreText), ["16", "26"])
        vm.setPriceDeliveryActive(false)
    }

    // MARK: - 3. Direction 395 Whole Percents Across 1.0.8 Surfaces & Kept 1.0.9 Plumbing

    func testAll108SurfacesPrintWholePercentsAndKeep109StreamGatePlumbing() async throws {
        let dict = makeLiveEventDict(
            awayScore: 14,
            homeScore: 20,
            homeProbability: 0.6357,
            awayProbability: 0.3643
        )
        let item = try decodeSnake(FeedItem.self, dict)
        let liveEvent = try XCTUnwrap(item.event)

        let suiteName = "FailClosed13634.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        // Default environment (`liveOddsRefreshActive == false`) used across ALL 1.0.8 cards
        // (Discover 30s, Sports tab 30s, My Stuff 15s, Search, Team, League, Sport, Hub).
        let defaultEventCard = EventCardView(event: liveEvent, reason: nil)
            .environmentObject(pinManager)
            .padding(16)
        let defaultEventOCR = try ocrStrings(renderAt390(defaultEventCard)).joined(separator: " ")
        XCTAssertTrue(defaultEventOCR.contains("64%") && defaultEventOCR.contains("36%"), "1.0.8 card surface must print whole percents: \(defaultEventOCR)")
        XCTAssertFalse(defaultEventOCR.contains("63.6%") || defaultEventOCR.contains("36.4%"), "1.0.8 card surface must never print tenths: \(defaultEventOCR)")

        let defaultDiscoverCard = NativeEventDiscoverCard(
            event: liveEvent,
            feedContext: nil,
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        )
        .environmentObject(pinManager)
        .padding(14)
        let defaultDiscoverOCR = try ocrStrings(renderAt390(defaultDiscoverCard)).joined(separator: " ")
        XCTAssertTrue(defaultDiscoverOCR.contains("64%") && defaultDiscoverOCR.contains("36%"), "1.0.8 Discover card must print whole percents: \(defaultDiscoverOCR)")
        XCTAssertFalse(defaultDiscoverOCR.contains("63.6%") || defaultDiscoverOCR.contains("36.4%"), "1.0.8 Discover card must never print tenths: \(defaultDiscoverOCR)")

        // Kept 1.0.9 plumbing (`liveOddsRefreshActive == true`, unused in 1.0.8; reserved for
        // per-card sub-second SSE streams in 1.0.9).
        let streamedPlumbingCard = EventCardView(event: liveEvent, reason: nil)
            .environment(\.liveOddsRefreshActive, true)
            .environmentObject(pinManager)
            .padding(16)
        let streamedPlumbingOCR = try ocrStrings(renderAt390(streamedPlumbingCard)).joined(separator: " ")
        XCTAssertTrue(streamedPlumbingOCR.contains("63.6%") && streamedPlumbingOCR.contains("36.4%"), "1.0.9 stream opt-in plumbing must still support tenths: \(streamedPlumbingOCR)")

        // FeedViewModel and MyStuffViewModel keep timer health tracking without setting tenths in 1.0.8.
        let feedResponse = try makeFeedResponse(itemDicts: [dict])
        let sportsClient = FailingSportsClient(feed: feedResponse)
        let sportsVM = FeedViewModel(client: sportsClient, telemetry: nil, autoRefreshEnabled: true)
        await sportsVM.startLoad()
        XCTAssertTrue(sportsVM.liveOddsRefreshRunning)
        sportsClient.setFail(true)
        await sportsVM.startLoad()
        XCTAssertFalse(sportsVM.liveOddsRefreshRunning)
        sportsVM.feedCovered()
        XCTAssertFalse(sportsVM.liveOddsRefreshRunning)
        sportsVM.viewDidStop()

        let myClient = FailingMyStuffClient(feed: feedResponse)
        let myVM = MyStuffViewModel(
            client: myClient,
            telemetry: nil,
            autoRefreshEnabled: true,
            optionalDeadline: 0.2,
            requiredAttempts: 1,
            retryBackoff: 0.01
        )
        await myVM.startLoad()
        XCTAssertTrue(myVM.liveOddsRefreshRunning)
        myClient.setFail(true)
        await myVM.startLoad()
        XCTAssertFalse(myVM.liveOddsRefreshRunning)
        myVM.viewDidStop()
    }

    // MARK: - 4. Simulator Proof Sheet (`0:00`, `+1:00`, and `Network off` — All Whole Percents at 390pt)

    func testSimulatorCaptureProofTwoMinutesApartAndNetworkOffAt390() async throws {
        let (initialDict, initialItem, nextItem): ([String: Any], FeedItem, FeedItem) = try {
            let env = ProcessInfo.processInfo.environment
            if let fixtureDir = env["LIVE_13634_FIXTURE_DIR"] ?? env["TEST_RUNNER_LIVE_13634_FIXTURE_DIR"],
               !fixtureDir.isEmpty {
                let p0 = URL(fileURLWithPath: fixtureDir).appendingPathComponent("t0_item.json")
                let p1 = URL(fileURLWithPath: fixtureDir).appendingPathComponent("t60_item.json")
                if FileManager.default.fileExists(atPath: p0.path),
                   FileManager.default.fileExists(atPath: p1.path),
                   let rawDict = try JSONSerialization.jsonObject(with: Data(contentsOf: p0)) as? [String: Any] {
                    let i0 = try JSONDecoder.snake13634.decode(FeedItem.self, from: Data(contentsOf: p0))
                    let i1 = try JSONDecoder.snake13634.decode(FeedItem.self, from: Data(contentsOf: p1))
                    return (rawDict, i0, i1)
                }
            }
            let dict0 = makeLiveEventDict(
                awayScore: 14,
                homeScore: 20,
                homeProbability: 0.6357,
                awayProbability: 0.3643,
                foldRevision: 1407,
                priceObservedAt: "2026-11-24T19:52:00Z",
                scoreObservedAt: "2026-11-24T19:51:50Z"
            )
            let dict1 = makeLiveEventDict(
                awayScore: 17,
                homeScore: 26,
                homeProbability: 0.6842,
                awayProbability: 0.3158,
                foldRevision: 1420,
                priceObservedAt: "2026-11-24T19:53:05Z",
                scoreObservedAt: "2026-11-24T19:53:00Z"
            )
            return (dict0, try decodeSnake(FeedItem.self, dict0), try decodeSnake(FeedItem.self, dict1))
        }()

        let event0 = try XCTUnwrap(initialItem.event)
        let event1 = try XCTUnwrap(nextItem.event)
        let prematch0 = PrematchReading.resolve(prematch: event0.prematchOdds, opening: event0.openingOdds)
        let chartHistory0 = try decodeSnake(EventHistoryResponse.self, [
            "event_id": event0.id,
            "home_team": event0.homeTeam,
            "away_team": event0.awayTeam,
            "status": "live",
            "blend_edge_pinned": false,
            "history": [],
            "aggregate_line": [
                ["timestamp": "2026-11-24T19:30:00Z", "home_probability": prematch0?.homeProbability ?? 0.50],
                ["timestamp": "2026-11-24T19:42:00Z", "home_probability": max(0.05, (event0.currentOdds?.homeProbability ?? 0.5) - 0.06)],
                ["timestamp": "2026-11-24T19:52:00Z", "home_probability": event0.currentOdds?.homeProbability ?? 0.5]
            ]
        ])

        let client = ScriptedDiscoverClient(
            feedResult: .success(try makeFeedResponse(itemDicts: [initialDict])),
            priceReplies: [.success(DiscoverPriceCards(items: [initialItem], dispositions: [initialItem.id: "updated"], builtAt: 200))]
        )
        let vm = DiscoverViewModel(
            client: client,
            priceClient: client,
            lastGood: nil,
            telemetry: nil,
            priceTickInterval: 0.03,
            liveRefreshInterval: 0.06,
            monitorNetworkPath: false
        )
        await vm.load()
        vm.setPriceDeliveryActive(true)
        vm.setPriceCardsVisible(owner: initialItem.id, cards: [initialItem], visible: true)
        let armed = await waitUntil { vm.livePriceRefreshRunning && client.priceCallCount >= 1 }
        XCTAssertTrue(armed)

        let suiteName = "Capture13634.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        func captureDiscoverCard() throws -> (UIImage, String) {
            let currentEvent = try XCTUnwrap(vm.items.first?.event)
            let card = NativeEventDiscoverCard(
                event: currentEvent,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: chartHistory0
            )
            .environmentObject(pinManager)
            .padding(14)
            let img = renderAt390(card, scheme: .light)
            let text = try ocrStrings(img).joined(separator: " ")
            return (img, text)
        }

        // Capture 1: t = 0:00 -> whole percents, zero decimals
        let (img0, ocr0) = try captureDiscoverCard()
        let wholeDuel0 = duelPercents(
            away: event0.currentOdds?.awayProbability,
            home: event0.currentOdds?.homeProbability,
            servedAway: event0.currentOdds?.awayRenderedPercent,
            servedHome: event0.currentOdds?.homeRenderedPercent
        )
        if let h0 = event0.currentOdds?.homeProbability {
            let wholeHome0 = formatProbability(h0, renderedPercent: wholeDuel0[1])
            XCTAssertTrue(ocr0.contains(wholeHome0), "Capture t=0 must print whole percent \(wholeHome0): \(ocr0)")
        }
        XCTAssertNil(ocr0.range(of: #"\d+\.\d+%"#, options: .regularExpression), "Capture t=0 must show zero decimals: \(ocr0)")

        // Capture 2: ~1 minute later -> whole percents and score moved cleanly, zero decimals
        client.setPriceReplies([
            .success(DiscoverPriceCards(items: [nextItem], dispositions: [initialItem.id: "updated"], builtAt: 201))
        ])
        let moved = await waitUntil(timeout: 6.0) {
            vm.items.first?.event?.currentOdds?.homeProbability == event1.currentOdds?.homeProbability
                && vm.items.first?.event?.homeScore == event1.homeScore
                && vm.items.first?.event?.awayScore == event1.awayScore
        }
        XCTAssertTrue(moved, "DiscoverViewModel must adopt moved +1m odds and score")
        let (img1, ocr1) = try captureDiscoverCard()
        let wholeDuel1 = duelPercents(
            away: event1.currentOdds?.awayProbability,
            home: event1.currentOdds?.homeProbability,
            servedAway: event1.currentOdds?.awayRenderedPercent,
            servedHome: event1.currentOdds?.homeRenderedPercent
        )
        if let h1 = event1.currentOdds?.homeProbability {
            let wholeHome1 = formatProbability(h1, renderedPercent: wholeDuel1[1])
            XCTAssertTrue(ocr1.contains(wholeHome1), "Capture +1:00 must print moved whole percent \(wholeHome1): \(ocr1)")
        }
        XCTAssertNotEqual(wholeDuel0[1], wholeDuel1[1], "Capture +1:00 must show moved whole percent across the two reads")
        XCTAssertNil(ocr1.range(of: #"\d+\.\d+%"#, options: .regularExpression), "Capture +1:00 must show zero decimals: \(ocr1)")

        // Capture 3: Network off -> stays whole percents, zero decimals
        client.setPriceReplies([.failure(URLError(.notConnectedToInternet))])
        let wentOffline = await waitUntil(timeout: 6.0) { !vm.livePriceRefreshRunning }
        XCTAssertTrue(wentOffline)
        let (imgOffline, ocrOffline) = try captureDiscoverCard()
        if let homeProb = event1.currentOdds?.homeProbability {
            let wholeHome = formatProbability(homeProb, renderedPercent: wholeDuel1[1])
            XCTAssertTrue(ocrOffline.contains(wholeHome), "Offline capture must print whole percent \(wholeHome): \(ocrOffline)")
        }
        XCTAssertNil(ocrOffline.range(of: #"\d+\.\d+%"#, options: .regularExpression), "Offline capture must contain zero fractional percentages: \(ocrOffline)")

        let env = ProcessInfo.processInfo.environment
        if let outDir = env["OUTPUT_DIR"] ?? env["TEST_RUNNER_OUTPUT_DIR"], !outDir.isEmpty {
            let dir = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try XCTUnwrap(img0.pngData()).write(to: dir.appendingPathComponent("capture_t0.png"))
            try XCTUnwrap(img1.pngData()).write(to: dir.appendingPathComponent("capture_t60.png"))
            try XCTUnwrap(imgOffline.pngData()).write(to: dir.appendingPathComponent("capture_offline.png"))
        }

        vm.setPriceDeliveryActive(false)
    }
}

private extension JSONDecoder {
    static var snake13634: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}
