import XCTest
@testable import Bain_Luck

@MainActor final class WatchForegroundUpdatesTests: XCTestCase {
    private final class Handle: LiveStreamHandle {
        var isClosed = false
        var closes = 0
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true; closes += 1 }
        func fire(_ event: String, _ raw: String) { handlers[event]?.forEach { $0(raw) } }
    }
    private actor Detail: WatchSelectedGameTransport {
        var calls = 0
        func fetch(eventID: Int) async throws -> WatchSelectedGame {
            calls += 1
            return try WatchForegroundUpdatesTests.game(revision: calls, home: calls == 1 ? 0.50 : 0.61)
        }
    }
    nonisolated private static func game(revision: Int, home: Double = 0.6, status: String = "live",
                                         scoreClock: String = "2026-10-10T09:00:00Z",
                                         priceClock: String = "2026-10-10T09:00:00Z") throws -> WatchSelectedGame {
        let object: [String: Any] = ["id": 101, "home_team": "Home", "away_team": "Away", "status": status,
            "hero_probability": home, "hero_probability_away": 0.29,
            "hero_probability_source": "blend", "hero_probability_observed_at": priceClock,
            "score_observed_at": scoreClock, "sport": "soccer_epl",
            "current_odds": ["draw_probability": 0.10], "blend_fold_revision": ["101": revision]]
        return try JSONDecoder().decode(WatchSelectedGame.self, from: JSONSerialization.data(withJSONObject: object))
    }

    func testOneVisibleStreamRefreshesAuthoritativeDetailWithoutPaintingRawFrame() async throws {
        let name = "watch-stream-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let transport = Detail()
        let selected = WatchSelectedGameStore(transport: transport, defaults: defaults, retryClock: { clock })
        selected.select(eventID: 101)
        let handle = Handle()
        var opens = 0, sleeps = 0
        await selected.runLiveForegroundRefresh(open: { id in
            XCTAssertEqual(id, 101); opens += 1; return handle
        }, clock: { clock }, sleep: { seconds in
            sleeps += 1
            if selected.successfulRefreshSequence == 2 || sleeps > 10 { throw CancellationError() }
            clock += seconds
            if sleeps == 1 {
                handle.fire("probability", #"{"event_id":101,"p":0.99,"rev":{"101":2}}"#)
            }
        })
        XCTAssertEqual(selected.successfulRefreshSequence, 2)
        XCTAssertEqual(selected.game?.homeProbability, 0.61)
        XCTAssertEqual(selected.game?.awayProbability, 0.29)
        XCTAssertEqual(selected.game?.drawProbability, 0.10)
        XCTAssertEqual(selected.game?.probabilitySource, "blend")
        XCTAssertLessThan(clock - 1_000, 30)
        XCTAssertEqual(opens, 1)
        XCTAssertEqual(handle.closes, 1)
    }

    func testInvalidationDuringFetchEarnsOneFollowupAndDuplicatesDoNot() {
        let signal = WatchForegroundInvalidation()
        let first = LiveStreamFrame(eventId: 101, p: 0.5, source: nil, sourceValue: nil,
            updatedAt: nil, status: nil, rev: .init(FoldRevision(["101": 1])))
        let newer = LiveStreamFrame(eventId: 101, p: 0.6, source: nil, sourceValue: nil,
            updatedAt: nil, status: nil, rev: .init(FoldRevision(["101": 2])))
        signal.receive(first, eventID: 101)
        signal.take(at: 100)
        signal.receive(newer, eventID: 101)
        signal.receive(newer, eventID: 101)
        signal.receive(first, eventID: 101)
        XCTAssertTrue(signal.pending)
        XCTAssertEqual(signal.delay(at: 101), 1)
        signal.take(at: 102)
        signal.receive(newer, eventID: 101)
        XCTAssertFalse(signal.pending)
        signal.receive(newer, eventID: 202)
        XCTAssertFalse(signal.pending)
    }

    func testResyncIsDedupedPerConnectionAndNeverPaintsAPrice() {
        let handle = Handle()
        var resyncs = 0
        let controller = LiveStreamController(open: { handle }, now: { 100 },
            onFrame: { _ in XCTFail("Recovery is not a price") }, onDeliveringChange: { _ in },
            onResync: { resyncs += 1 })
        controller.start()
        handle.fire("resync", #"{"generation":1}"#)
        handle.fire("resync", #"{"generation":1}"#)
        handle.fire("resync", #"{"generation":2}"#)
        XCTAssertEqual(resyncs, 2)
        handle.fire("open", "")
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(resyncs, 3)
        controller.stop()
    }

    func testRevisionAndObservationClocksCannotRegressTogether() throws {
        let held = try Self.game(revision: 8)
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 7), replacing: held))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9,
            scoreClock: "2026-10-10T08:00:00Z"), replacing: held))
        // Removing a source can produce a newer fold with an older price observation.
        XCTAssertTrue(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9,
            priceClock: "2026-10-10T08:00:00Z"), replacing: held))
        let final = try Self.game(revision: 8, status: "final")
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.game(revision: 9), replacing: final))
    }
}
