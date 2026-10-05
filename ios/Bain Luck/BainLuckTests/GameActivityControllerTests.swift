#if os(iOS) && canImport(ActivityKit)
import XCTest
import Combine
import UIKit
@testable import Bain_Luck

@MainActor private final class FakeGameActivityService: GameActivityServing {
    var isEnabled = true
    var records: [GameActivityRecord] = []
    var requestFails = false
    var requests = 0
    var updates: [(String, GameActivitySnapshot, Date)] = []
    var ends: [(String, GameActivitySnapshot?)] = []
    var suspendNextUpdate = false
    private var suspendedUpdate: CheckedContinuation<Void, Never>?
    private var pauseObserver: CheckedContinuation<Void, Never>?
    var didUpdate: ((GameActivitySnapshot, Date) -> Void)?

    func waitUntilUpdateIsSuspended() async {
        if suspendedUpdate != nil { return }
        await withCheckedContinuation { pauseObserver = $0 }
    }
    func releaseSuspendedUpdate() {
        let continuation = suspendedUpdate
        suspendedUpdate = nil
        continuation?.resume()
    }
    func request(_ snapshot: GameActivitySnapshot, staleDate: Date) throws {
        requests += 1
        if requestFails { throw NSError(domain: "FakeActivity", code: 1) }
        records.append(GameActivityRecord(id: "activity-\(snapshot.eventID)",
                                          eventID: snapshot.eventID, snapshot: snapshot))
        updates.append(("activity-\(snapshot.eventID)", snapshot, staleDate))
    }
    func update(id: String, snapshot: GameActivitySnapshot, staleDate: Date) async {
        if suspendNextUpdate {
            suspendNextUpdate = false
            await withCheckedContinuation { continuation in
                suspendedUpdate = continuation
                pauseObserver?.resume()
                pauseObserver = nil
            }
        }
        updates.append((id, snapshot, staleDate))
        if let index = records.firstIndex(where: { $0.id == id }) {
            records[index] = GameActivityRecord(id: id, eventID: snapshot.eventID, snapshot: snapshot)
        }
        didUpdate?(snapshot, staleDate)
    }
    func end(id: String, final: GameActivitySnapshot?) async {
        ends.append((id, final))
        records.removeAll { $0.id == id }
    }
}

final class GameActivityControllerTests: XCTestCase {
    private let clock = Date(timeIntervalSince1970: 1_759_752_000)
    @MainActor private func snapshot(_ id: Int = 1, status: String = "live", clock: Date? = nil,
                          scoreClock: Date? = nil, scores: Bool = false) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(eventID: id, homeTeam: "Home", awayTeam: "Away",
                                           status: status, homeScore: scores ? 2 : nil,
                                           awayScore: scores ? 1 : nil, homeProbability: 0.64,
                                           sport: "soccer", scoreObservedAt: scoreClock,
                                           probabilityObservedAt: clock))
    }

    @MainActor func testExplicitStartDoesNotReplaceExistingOrStartTerminalGame() throws {
        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
        controller.start(snapshot: try snapshot(clock: clock))
        XCTAssertEqual(service.requests, 1)
        XCTAssertEqual(controller.activeEventIDs, [1])
        controller.start(snapshot: try snapshot(2, clock: clock))
        controller.start(snapshot: try snapshot(clock: clock))
        XCTAssertEqual(service.requests, 1)
        let terminalService = FakeGameActivityService()
        let terminal = GameActivityController(service: terminalService, isForeground: { true })
        terminal.start(snapshot: try snapshot(status: "completed"))
        XCTAssertEqual(terminalService.requests, 0)
    }

    @MainActor func testDisabledBackgroundAndRequestFailureRemainVisible() throws {
        let service = FakeGameActivityService()
        service.isEnabled = false
        let disabled = GameActivityController(service: service, isForeground: { true })
        disabled.start(snapshot: try snapshot())
        XCTAssertEqual(service.requests, 0)
        XCTAssertTrue(disabled.status?.contains("disabled") == true)
        service.isEnabled = true
        let background = GameActivityController(service: service, isForeground: { false })
        background.start(snapshot: try snapshot())
        XCTAssertEqual(service.requests, 0)
        service.requestFails = true
        let failing = GameActivityController(service: service, isForeground: { true })
        failing.start(snapshot: try snapshot())
        XCTAssertTrue(failing.activeEventIDs.isEmpty)
        XCTAssertTrue(failing.status?.contains("Couldn't start") == true)
    }

    @MainActor func testReturningFromSettingsRevealsPreviouslyDisabledControl() async {
        let service = FakeGameActivityService()
        service.isEnabled = false
        let notifications = NotificationCenter()
        let controller = GameActivityController(service: service, isForeground: { true },
                                                notificationCenter: notifications)
        XCTAssertFalse(GameActivityControlPresentation(isPhone: true, isEnabled: controller.isEnabled,
            isTerminal: false, isActive: false).showsControl)
        let reconciled = expectation(description: "Availability refreshed after app activation")
        let observation = controller.$isEnabled.filter { $0 }.first().sink { _ in reconciled.fulfill() }
        service.isEnabled = true
        notifications.post(name: UIApplication.didBecomeActiveNotification, object: nil)
        await fulfillment(of: [reconciled], timeout: 2)
        XCTAssertTrue(GameActivityControlPresentation(isPhone: true, isEnabled: controller.isEnabled,
            isTerminal: false, isActive: false).showsControl)
        XCTAssertEqual(service.requests, 0, "Returning from Settings never implicitly starts an activity")
        withExtendedLifetime(observation) {}
    }

    @MainActor func testReconcileAndExplicitStopTouchOnlyRequestedGame() async throws {
        let service = FakeGameActivityService()
        service.records = [GameActivityRecord(id: "existing", eventID: 2, snapshot: try snapshot(2))]
        let controller = GameActivityController(service: service, isForeground: { true })
        XCTAssertEqual(controller.activeEventIDs, [2])
        await controller.stop(eventID: 1)
        XCTAssertTrue(service.ends.isEmpty)
        await controller.stop(eventID: 2)
        XCTAssertEqual(service.ends.map(\.0), ["existing"])
        XCTAssertTrue(controller.activeEventIDs.isEmpty)
    }

    @MainActor func testProducerClockExpiryUnknownScoreClockAndSuspension() async throws {
        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
        controller.start(snapshot: try snapshot(clock: clock.addingTimeInterval(-30)))
        XCTAssertEqual(service.updates.last?.2, clock.addingTimeInterval(90))
        await controller.update(snapshot: try snapshot(clock: clock, scores: true))
        XCTAssertEqual(service.updates.last?.2, clock, "An unknown score clock cannot be dated by a probability")
        await controller.markStale(eventID: 1)
        XCTAssertEqual(service.updates.last?.2, clock)
    }

    @MainActor func testOlderObservationIsRejectedAndAuthoritativeFinalEndsActivity() async throws {
        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
        controller.start(snapshot: try snapshot(clock: clock))
        await controller.update(snapshot: try snapshot(clock: clock.addingTimeInterval(-1)))
        XCTAssertEqual(service.updates.count, 1)
        await controller.update(snapshot: try snapshot(status: "completed", scores: true))
        XCTAssertEqual(service.ends.count, 1)
        XCTAssertTrue(service.ends.first?.1?.isFinal == true)
        XCTAssertTrue(controller.activeEventIDs.isEmpty)
    }

    @MainActor func testUnknownClocksCannotEraseKnownObservationFences() async throws {
        for testingScore in [false, true] {
            let service = FakeGameActivityService()
            let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
            controller.start(snapshot: try snapshot(clock: clock,
                scoreClock: testingScore ? clock : nil, scores: testingScore))
            await controller.update(snapshot: try snapshot(clock: testingScore ? clock : nil,
                scores: testingScore))
            let writesAfterUnknown = service.updates.count
            await controller.update(snapshot: try snapshot(
                clock: testingScore ? clock : clock.addingTimeInterval(-1),
                scoreClock: testingScore ? clock.addingTimeInterval(-1) : nil, scores: testingScore))
            XCTAssertEqual(service.updates.count, writesAfterUnknown,
                           "Missing \(testingScore ? "score" : "price") clock cannot erase its independent ordering fence")
        }
    }

    @MainActor func testAuthoritativeFinalEndsEvenWhenItsScoreClockIsOlder() async throws {
        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
        controller.start(snapshot: try snapshot(clock: clock, scoreClock: clock, scores: true))
        await controller.update(snapshot: try snapshot(status: "completed",
            scoreClock: clock.addingTimeInterval(-1), scores: true))
        let final = try XCTUnwrap(service.ends.first?.1)
        XCTAssertTrue(final.isFinal)
        XCTAssertNil(final.probabilityText)
        XCTAssertEqual(final.scoreObservedAt, clock.addingTimeInterval(-1),
                       "Terminal adoption must preserve its real producer clock, never replace it with receipt time")
        XCTAssertTrue(controller.activeEventIDs.isEmpty)
    }

    @MainActor func testDepartureWinsOverQueuedUpdateWhileApplicationRemainsActive() async throws {
        let service = FakeGameActivityService()
        let controller = GameActivityController(service: service, isForeground: { true }, now: { self.clock })
        controller.start(snapshot: try snapshot(clock: clock.addingTimeInterval(-30)))
        service.suspendNextUpdate = true
        let first = try snapshot(clock: clock.addingTimeInterval(-20))
        let operation = Task { await controller.update(snapshot: first) }
        await service.waitUntilUpdateIsSuspended()
        await controller.update(snapshot: try snapshot(clock: clock.addingTimeInterval(-10)))
        await controller.markStale(eventID: 1)
        service.releaseSuspendedUpdate()
        await operation.value
        XCTAssertEqual(service.updates.last?.2, clock, "The final departure write must mark the retained reading stale")

        // Catch the old detached drain task, which could renew expiry after the
        // markStale operation returned, even though its page had disappeared.
        let renewed = expectation(description: "Departed page must not renew the activity")
        renewed.isInverted = true
        service.didUpdate = { _, staleDate in
            if staleDate > self.clock { renewed.fulfill() }
        }
        await controller.update(snapshot: try snapshot(clock: clock))
        await fulfillment(of: [renewed], timeout: 0.1)
        XCTAssertEqual(service.updates.last?.2, clock)
    }
}
#endif
