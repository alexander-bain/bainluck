import XCTest
@testable import Bain_Luck

/// #13509 + #13504 — unit proof on `apple/13509-13504-app-fixes`:
/// 1. When a live price frame arrives for a three-way game (carrying `draw_probability`),
///    neither `EventDetailViewModel` nor `LiveEventPriceReconciliation` sets `away = 1 - p`.
///    All three served numbers keep adding to 100 with the favourite unchanged until the next full read.
/// 2. Two-way games (`draw_probability == nil`) still adopt pushed prices and `away = 1 - p` as today.
/// 3. Onboarding picked-team chips grow their adaptive column minimum on regular-width (iPad) canvases.
@MainActor
final class ThreeWayLiveStreamGuard13509Tests: XCTestCase {

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    private struct StaticClient: EventDetailProviding {
        struct Missing: Error {}
        var event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeFrame(_ json: String) throws -> LiveStreamFrame {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(LiveStreamFrame.self, from: Data(json.utf8))
    }

    private func threeWaySoccerEvent(
        id: Int = 15344466,
        home: Double = 0.26445,
        draw: Double = 0.400011,
        away: Double = 0.335539,
        rev: Int = 10
    ) throws -> EventDetail {
        try decodeEvent("""
        {
          "id": \(id),
          "sport": "soccer_greece_super_league",
          "home_team": "Asteras Tripolis",
          "away_team": "Aris Thessaloniki",
          "status": "live",
          "home_score": 0,
          "away_score": 0,
          "current_odds": {
            "home_probability": \(home),
            "draw_probability": \(draw),
            "away_probability": \(away),
            "home_rendered_percent": 26,
            "away_rendered_percent": 34
          },
          "hero_probability": \(home),
          "hero_probability_away": \(away),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-23T15:39:00Z",
          "blend_fold_revision": {"\(id)": \(rev)},
          "win_probability_sources": {
            "polymarket": {
              "value": \(home),
              "display_name": "Polymarket",
              "type": "market",
              "color": "#000000",
              "updated_at": "2026-11-23T15:39:00Z"
            }
          }
        }
        """)
    }

    private func twoWayBasketballEvent(
        id: Int = 4242,
        home: Double = 0.40,
        away: Double = 0.60,
        rev: Int = 10
    ) throws -> EventDetail {
        try decodeEvent("""
        {
          "id": \(id),
          "sport": "basketball_nba",
          "home_team": "76ers",
          "away_team": "Trail Blazers",
          "status": "live",
          "home_score": 52,
          "away_score": 50,
          "current_odds": {
            "home_probability": \(home),
            "away_probability": \(away),
            "home_rendered_percent": 40,
            "away_rendered_percent": 60
          },
          "hero_probability": \(home),
          "hero_probability_away": \(away),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-23T15:39:00Z",
          "blend_fold_revision": {"\(id)": \(rev)},
          "win_probability_sources": {
            "polymarket": {
              "value": \(home),
              "display_name": "Polymarket",
              "type": "market",
              "color": "#000000",
              "updated_at": "2026-11-23T15:39:00Z"
            }
          }
        }
        """)
    }

    func testThreeWayGameKeepsServedNumbersAndFavoriteAcrossPushedPrices() async throws {
        let initial = try threeWaySoccerEvent()
        let handle = FakeHandle()
        let vm = EventDetailViewModel(
            eventId: initial.id,
            client: StaticClient(event: initial),
            makeStreamHandle: { _ in handle },
            now: { 1_795_448_400 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        defer { vm.stopRefresh() }

        handle.fire("open")
        // Push two single-scalar price ticks + a folded_probability tick.
        handle.fire("probability", """
        {"event_id":15344466,"p":0.256,"source":"polymarket","source_value":0.256,"updated_at":"2026-11-23T15:40:00Z","status":"live","rev":{"15344466":11}}
        """)
        handle.fire("probability", """
        {"event_id":15344466,"p":0.240,"source":"polymarket","source_value":0.240,"updated_at":"2026-11-23T15:41:00Z","status":"live","rev":{"15344466":12}}
        """)
        handle.fire("folded_probability", """
        {"event_id":15344466,"p":0.230,"source":"polymarket","source_value":0.230,"updated_at":"2026-11-23T15:41:30Z","status":"live","rev":{"15344466":13},"folded_quote_pending":false,"folded_quote":{"event_id":15344466,"hero_probability":0.230,"hero_probability_away":0.770,"hero_probability_source":"blend","hero_probability_observed_at":"2026-11-23T15:41:30Z","blend_fold_revision":{"15344466":13},"win_probability_sources":{"polymarket":{"value":0.230,"display_name":"Polymarket","type":"market","color":"#000000","updated_at":"2026-11-23T15:41:30Z"}},"hero_sportsbook_count":null,"status":"live","sport":"soccer_greece_super_league","hero_settled_result":null}}
        """)

        let current = try XCTUnwrap(vm.event)
        let shown = vm.headline(current)
        let odds = try XCTUnwrap(shown.currentOdds)
        XCTAssertEqual(try XCTUnwrap(odds.homeProbability), 0.26445, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(odds.drawProbability), 0.400011, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(odds.awayProbability), 0.335539, accuracy: 1e-6)
        XCTAssertNotEqual(try XCTUnwrap(odds.awayProbability), 1 - 0.240, accuracy: 1e-3)

        let scaled = EventAtlasSoccerCards11666.scaleThreeWayField(
            home: odds.homeProbability,
            draw: odds.drawProbability,
            away: odds.awayProbability
        )
        let home = try XCTUnwrap(scaled.home)
        let draw = try XCTUnwrap(scaled.draw)
        let away = try XCTUnwrap(scaled.away)
        // Draw stays the favourite and the three shares sum to 100%.
        XCTAssertGreaterThan(draw, away)
        XCTAssertGreaterThan(away, home)
        XCTAssertEqual((home + draw + away) * 100.0, 100.0, accuracy: 0.01)
    }

    func testReconciliationLeavesThreeWayPolledEventIntact() throws {
        let polled = try threeWaySoccerEvent()
        let frame = try decodeFrame("""
        {"event_id":15344466,"p":0.256,"source":"polymarket","source_value":0.256,"updated_at":"2026-11-23T15:42:00Z","status":"live","rev":{"15344466":15}}
        """)
        XCTAssertFalse(LiveEventPriceReconciliation.shouldPreserve(frame, over: polled, streamRecoverable: true))
        let reconciled = LiveEventPriceReconciliation.applying(frame, to: polled, streamRecoverable: true)
        XCTAssertEqual(try XCTUnwrap(reconciled.currentOdds?.homeProbability), 0.26445, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(reconciled.currentOdds?.drawProbability), 0.400011, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(reconciled.currentOdds?.awayProbability), 0.335539, accuracy: 1e-6)
    }

    func testTwoWayGameStillAdoptsPushedPriceAndComplement() async throws {
        let initial = try twoWayBasketballEvent()
        let handle = FakeHandle()
        let vm = EventDetailViewModel(
            eventId: initial.id,
            client: StaticClient(event: initial),
            makeStreamHandle: { _ in handle },
            now: { 1_795_448_400 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        defer { vm.stopRefresh() }

        handle.fire("open")
        let frameJSON = """
        {"event_id":4242,"p":0.62,"source":"polymarket","source_value":0.62,"updated_at":"2026-11-23T15:40:00Z","status":"live","rev":{"4242":11}}
        """
        handle.fire("probability", frameJSON)

        let updatedOdds = try XCTUnwrap(vm.event?.currentOdds)
        XCTAssertEqual(try XCTUnwrap(updatedOdds.homeProbability), 0.62, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(updatedOdds.awayProbability), 0.38, accuracy: 1e-6)
        XCTAssertNil(updatedOdds.homeRenderedPercent)
        XCTAssertNil(updatedOdds.awayRenderedPercent)

        let frame = try decodeFrame(frameJSON)
        XCTAssertTrue(LiveEventPriceReconciliation.shouldPreserve(frame, over: initial, streamRecoverable: true))
        let reconciled = LiveEventPriceReconciliation.applying(frame, to: initial, streamRecoverable: true)
        XCTAssertEqual(try XCTUnwrap(reconciled.currentOdds?.homeProbability), 0.62, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(reconciled.currentOdds?.awayProbability), 0.38, accuracy: 1e-6)
    }

    func testOnboardingChipMinimumWidthGrowsOnRegularWidth() {
        XCTAssertEqual(OnboardingView.selectedChipMinimumWidth(regularWidth: false), 140)
        XCTAssertGreaterThanOrEqual(OnboardingView.selectedChipMinimumWidth(regularWidth: true), 240)
    }
}
