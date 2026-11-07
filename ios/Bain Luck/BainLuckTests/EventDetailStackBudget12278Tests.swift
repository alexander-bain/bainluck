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

    private func sampleEventDetail() throws -> EventDetail {
        let json = """
        {
          "id": 15342680,
          "sport": "americanfootball_nfl",
          "league": "NFL",
          "home_team": "Washington Commanders",
          "away_team": "San Francisco 49ers",
          "commence_time": "2026-11-08T18:00:00Z",
          "status": "live",
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
            "period": 3,
            "game_clock": "6:12",
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "home_win_prob": 0.36, "away_win_prob": 0.64, "weight": 3.0 },
            "kalshi": { "home_win_prob": 0.37, "away_win_prob": 0.63, "weight": 0.8 },
            "polymarket": { "home_win_prob": 0.365, "away_win_prob": 0.635, "weight": 0.8 }
          },
          "bookmaker_odds": [
            {
              "bookmaker": "fanduel",
              "home_probability": 0.36,
              "away_probability": 0.64,
              "captured_at": "2026-11-07T17:29:00Z"
            },
            {
              "bookmaker": "draftkings",
              "home_probability": 0.37,
              "away_probability": 0.63,
              "captured_at": "2026-11-07T17:29:30Z"
            }
          ]
        }
        """
        return try JSONDecoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    @MainActor
    func testEventDetailViewBodyAndSectionSubtreesFitWithinStackBudget() throws {
        XCTAssertTrue(
            ReleaseSurfaces.eventPageAtlasEnabled,
            "ReleaseSurfaces.eventPageAtlasEnabled must be true (85-A / #12278)"
        )
        XCTAssertTrue(ReleaseSurfaces.isEventPageAtlasEnabled())

        let event = try sampleEventDetail()
        let view = EventDetailView(eventId: event.id)
        let bodySize = MemoryLayout.size(ofValue: view.body)
        let contentSize = view.contentViewValueSizeForTest12278
        let heroSize = view.heroSectionValueSizeForTest12278(event)
        let headline = try XCTUnwrap(
            NFLPairedHeadline9483.priced(
                awayText: "63.6%",
                homeText: "36.4%",
                live: true,
                score: (away: 21, home: 17),
                pregame: PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
            )
        )
        let pairedHeadlineSize = view.nflPairedHeadlineValueSizeForTest12278(event, headline)

        XCTAssertEqual(bodySize, MemoryLayout<AnyView>.size)
        XCTAssertLessThanOrEqual(bodySize, 64)
        XCTAssertLessThanOrEqual(contentSize, 64)
        XCTAssertLessThanOrEqual(heroSize, 64)
        XCTAssertLessThanOrEqual(pairedHeadlineSize, 64)
    }

    @MainActor
    func testEventDetailViewRendersAtPhoneWidthAndExecutesOnConstrained256KBStack() throws {
        let event = try sampleEventDetail()
        let headline = try XCTUnwrap(
            NFLPairedHeadline9483.priced(
                awayText: "63.6%",
                homeText: "36.4%",
                live: true,
                score: (away: 21, home: 17),
                pregame: PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
            )
        )

        // 1. Host and lay out at 390x844 phone width on the main actor.
        let view = EventDetailView(eventId: event.id)
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

        // 2. Evaluate body, contentView, heroSection, and nflPairedHeadlineView
        // on a secondary thread with a 256 KB stack (1/4 of the 1,008 KB iPhone
        // Thread 0 stack that previously overflowed at 1,004,336 bytes).
        let finished = expectation(description: "256 KB stack evaluation finished without overflow")
        var observedSizes: (body: Int, content: Int, hero: Int, paired: Int)?
        let thread = Thread {
            let workerView = EventDetailView(eventId: event.id)
            let b = MemoryLayout.size(ofValue: workerView.body)
            let c = workerView.contentViewValueSizeForTest12278
            let h = workerView.heroSectionValueSizeForTest12278(event)
            let p = workerView.nflPairedHeadlineValueSizeForTest12278(event, headline)
            observedSizes = (b, c, h, p)
            finished.fulfill()
        }
        thread.stackSize = 256 * 1024
        thread.start()
        wait(for: [finished], timeout: 5.0)

        let sizes = try XCTUnwrap(observedSizes)
        XCTAssertLessThanOrEqual(sizes.body, 64)
        XCTAssertLessThanOrEqual(sizes.content, 64)
        XCTAssertLessThanOrEqual(sizes.hero, 64)
        XCTAssertLessThanOrEqual(sizes.paired, 64)
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
