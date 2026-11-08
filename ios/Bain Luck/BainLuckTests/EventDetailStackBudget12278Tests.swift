import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12278 — TestFlight build 5670 (`1.0.6 (5670)`, commit `d8f7c15e59`) and
/// build 5668 (`c0165730fd`) crashed on iPhone (`iPhone19,3`, iOS `27.0.1`)
/// with `EXC_BAD_ACCESS (SIGSEGV)` / `KERN_PROTECTION_FAILURE` in `Thread 0`
/// `Stack Guard` inside `EventDetailView.heroSection(_:) ->
/// __swift_instantiateConcreteTypeFromMangledNameV2`.
final class EventDetailStackBudget12278Tests: XCTestCase {

    private final class LockedResultBox<Value>: @unchecked Sendable {
        private let lock = NSLock()
        private var storage: Value?

        func store(_ value: Value) {
            lock.lock()
            storage = value
            lock.unlock()
        }

        func load() -> Value? {
            lock.lock()
            defer { lock.unlock() }
            return storage
        }
    }

    private func sampleEventDetail(
        status: String = "live",
        sport: String = "americanfootball_nfl"
    ) throws -> EventDetail {
        let json = """
        {
          "id": 15342680,
          "sport": "\(sport)",
          "league": "NFL",
          "home_team": "Washington Commanders",
          "away_team": "San Francisco 49ers",
          "commence_time": "2026-11-08T18:00:00Z",
          "status": "\(status)",
          "home_score": 17,
          "away_score": 21,
          "current_odds": {
            "home_probability": 0.364,
            "away_probability": 0.636,
            "home_rendered_percent": 36,
            "away_rendered_percent": 64,
            "updated_at": "2026-11-07T17:30:00Z"
          },
          "opening_odds": {
            "home_probability": 0.44,
            "away_probability": 0.56,
            "home_rendered_percent": 44,
            "away_rendered_percent": 56
          },
          "prematch_odds": {
            "home_probability": 0.42,
            "away_probability": 0.58,
            "home_rendered_percent": 42,
            "away_rendered_percent": 58
          },
          "espn": {
            "period": "3",
            "game_clock": "6:12",
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "value": 0.36, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.37, "display_name": "Kalshi" },
            "polymarket": { "value": 0.365, "display_name": "Polymarket" }
          }
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    @MainActor
    func testEventDetailViewBodyAndSectionSubtreesFitWithinStackBudget() throws {
        XCTAssertTrue(
            ReleaseSurfaces.eventPageAtlasEnabled,
            "ReleaseSurfaces.eventPageAtlasEnabled must be true (85-A / #12278)"
        )
        XCTAssertTrue(ReleaseSurfaces.isEventPageAtlasEnabled())

        let event = try sampleEventDetail()
        let view = EventDetailView(eventId: event.id).withLoadedEventForTest12278(event)
        let bodySize = MemoryLayout.size(ofValue: view.body)
        let contentSize = view.contentViewValueSizeForTest12278
        let heroSize = view.heroSectionValueSizeForTest12278(event)
        let pairedHeadlineSize = try XCTUnwrap(view.nflPairedHeadlineValueSizeForTest12278(event))

        XCTAssertLessThanOrEqual(
            bodySize,
            64,
            "EventDetailView.body value size (\(bodySize) bytes) must stay <= 64 bytes (#12278)"
        )
        XCTAssertLessThanOrEqual(contentSize, 64)
        XCTAssertLessThanOrEqual(heroSize, 64)
        XCTAssertLessThanOrEqual(pairedHeadlineSize, 64)
    }

    @MainActor
    func testEventDetailViewRendersAtPhoneWidthAndExecutesOnConstrained256KBStack() throws {
        let liveEvent = try sampleEventDetail(status: "live", sport: "americanfootball_nfl")
        let finishedEvent = try sampleEventDetail(status: "completed", sport: "americanfootball_nfl")
        let scheduledEvent = try sampleEventDetail(status: "scheduled", sport: "soccer_epl")

        // 1. Host and lay out at 390x844 phone width on the main actor with a loaded EventDetail.
        let view = EventDetailView(eventId: liveEvent.id).withLoadedEventForTest12278(liveEvent)
        let host = UIHostingController(
            rootView: NavigationStack {
                view
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
        )
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        XCTAssertEqual(host.view.bounds.width, 390)

        // 2. Execute body, contentView, heroSection, and nflPairedHeadlineView
        // on the loaded EventDetail branch across live, finished, and scheduled
        // events on a secondary thread with a 256 KB stack (1/4 of the 1,008 KB
        // iPhone Thread 0 stack that previously overflowed at 1,004,336 bytes).
        let finished = expectation(description: "256 KB stack evaluation finished without overflow")
        let observedBox = LockedResultBox<(
            live: (bodySize: Int, contentSize: Int, heroSize: Int, pairedSize: Int?),
            finished: (bodySize: Int, contentSize: Int, heroSize: Int, pairedSize: Int?),
            scheduled: (bodySize: Int, contentSize: Int, heroSize: Int, pairedSize: Int?)
        )>()
        let thread = Thread {
            let workerView = EventDetailView(eventId: liveEvent.id)
            // evaluateViewTreeForTest12278 injects the decoded EventDetail via withLoadedEventForTest12278 so body and contentView execute the loaded event branch on this 256 KB stack.
            let liveSizes = workerView.evaluateViewTreeForTest12278(liveEvent)
            let finishedSizes = workerView.evaluateViewTreeForTest12278(finishedEvent)
            let scheduledSizes = workerView.evaluateViewTreeForTest12278(scheduledEvent)
            observedBox.store((live: liveSizes, finished: finishedSizes, scheduled: scheduledSizes))
            finished.fulfill()
        }
        thread.stackSize = 256 * 1024
        thread.start()
        wait(for: [finished], timeout: 5.0)

        let observed = try XCTUnwrap(observedBox.load())
        XCTAssertLessThanOrEqual(observed.live.bodySize, 64)
        XCTAssertLessThanOrEqual(observed.live.contentSize, 64)
        XCTAssertLessThanOrEqual(observed.live.heroSize, 64)
        XCTAssertLessThanOrEqual(try XCTUnwrap(observed.live.pairedSize), 64)
        XCTAssertLessThanOrEqual(observed.finished.bodySize, 64)
        XCTAssertLessThanOrEqual(observed.finished.contentSize, 64)
        XCTAssertLessThanOrEqual(observed.finished.heroSize, 64)
        XCTAssertLessThanOrEqual(observed.scheduled.bodySize, 64)
        XCTAssertLessThanOrEqual(observed.scheduled.contentSize, 64)
        XCTAssertLessThanOrEqual(observed.scheduled.heroSize, 64)
    }

    func testEventDetailViewSourcePreservesNonInlinedStackBoundaries() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        let source = try String(
            contentsOf: root.appendingPathComponent("Views/EventDetailView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(
            source.contains("@inline(never)\n    private func stackBoundary12278<V: View>(@ViewBuilder _ make: () -> V) -> AnyView"),
            "EventDetailView must keep @inline(never) stackBoundary12278 so Release (-O) cannot inline child @ViewBuilder frames into body/contentView/heroSection"
        )
        let boundaryOccurrences = source.components(separatedBy: "stackBoundary12278 {").count - 1
        XCTAssertGreaterThanOrEqual(
            boundaryOccurrences,
            24,
            "EventDetailView must preserve all 24+ stackBoundary12278 seams across body, contentView, heroSection, and nflPairedHeadlineView (found \(boundaryOccurrences))"
        )
    }

    @MainActor
    func testUniversalLinkEventRouteQueuesAndConsumesForFeedTab() throws {
        let nav = NavigationCoordinator()
        XCTAssertEqual(nav.selectedTab, .discover)

        XCTAssertTrue(
            nav.handleURL(try XCTUnwrap(URL(string: "https://www.bainluck.com/events/15342680?atlas=1")))
        )
        XCTAssertEqual(nav.selectedTab, .feed)

        let queued = expectation(description: "event route published after tab switch")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { queued.fulfill() }
        wait(for: [queued], timeout: 1.0)

        XCTAssertEqual(nav.pendingRoute, .eventDetail(id: 15342680))
        XCTAssertEqual(nav.consumeRoute(), .eventDetail(id: 15342680))
        XCTAssertNil(nav.consumeRoute(), "consumeRoute() must clear pendingRoute so a second observer never pushes twice")
    }
}
