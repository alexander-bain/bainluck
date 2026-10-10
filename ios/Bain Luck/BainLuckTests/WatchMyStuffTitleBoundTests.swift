#if os(iOS)
import XCTest
@testable import Bain_Luck

final class WatchMyStuffTitleBoundTests: XCTestCase {
    @MainActor func testActualPublisherDecodesUnicodeTitlesWithoutDroppingNeighbors() async throws {
        let name = "watch-title-bound-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let family = "👨‍👩‍👧‍👦"
        let longTitle = String(repeating: family, count: 400)
        let oversizedCluster = "a" + String(repeating: "\u{301}", count: 1500)
        XCTAssertEqual(longTitle.count, 400)
        XCTAssertEqual(oversizedCluster.count, 1)
        XCTAssertGreaterThan(oversizedCluster.utf8.count, WatchMyStuffSnapshot.maxTitleBytes)
        let identity = PinAccountBinding(userID: "account", authenticated: true)
        let pins = PinManager(defaults: defaults, initialBinding: identity,
            serverLoad: { PinsResponse(events: [101, 202], futures: []) })
        await pins.loadPins()
        let preferences = PreferencesResponse(homeLocation: nil, sportAffinities: [:], onboardingCompleted: true,
            favorites: [
                FavoriteItem(teamId: 7, teamName: oversizedCluster, relationType: "follow",
                    sportKey: nil, logoUrl: nil, source: nil),
                FavoriteItem(teamId: 8, teamName: "Ordinary team", relationType: "rival",
                    sportKey: nil, logoUrl: nil, source: nil)
            ])
        let publisher = WatchMyStuffPublisher(fetchPreferences: { preferences }, lookupPin: { pin in
            .available(title: pin.value == 101 ? longTitle : "Ordinary game")
        })
        let complete = expectation(description: "Actual publisher payload survives shared decoder")
        var captured: WatchMyStuffSnapshot?
        var publishedBytes = 0
        publisher.publish = { bytes in
            guard let value = WatchMyStuffSnapshot.decode(bytes, now: Date()),
                  value.teams.state == .loaded,
                  value.pins.items.first(where: { $0.targetID == 202 })?.title == "Ordinary game",
                  captured == nil else { return }
            captured = value; publishedBytes = bytes.count
            complete.fulfill()
        }
        publisher.bind(identity, pins: pins)
        await fulfillment(of: [complete], timeout: 2)
        let value = try XCTUnwrap(captured)
        XCTAssertEqual(value.pins.items.map(\.targetID), [101, 202])
        XCTAssertEqual(value.teams.items.map(\.targetID), [7, 8])
        let clipped = try XCTUnwrap(value.pins.items.first?.title)
        XCTAssertTrue(clipped.hasSuffix("…"))
        XCTAssertTrue(longTitle.hasPrefix(String(clipped.dropLast())))
        XCTAssertTrue(clipped.dropLast().allSatisfy { String($0) == family })
        XCTAssertLessThanOrEqual(clipped.utf8.count, WatchMyStuffSnapshot.maxTitleBytes)
        XCTAssertEqual(value.teams.items.first?.title, "…")
        XCTAssertEqual(value.teams.items.last?.title, "Ordinary team")
        XCTAssertLessThanOrEqual(publishedBytes, WatchMyStuffSnapshot.maxBytes)
        XCTAssertEqual(value.pins.omittedCount + value.teams.omittedCount, 0)
    }

    @MainActor func testOrdinaryTitlesRemainUnchangedAndEllipsisReservesBytes() {
        XCTAssertEqual(WatchMyStuffPublisher.boundedTitle("Café at home"), "Café at home")
        XCTAssertEqual(WatchMyStuffPublisher.boundedTitle(String(repeating: "A", count: 400)),
                       String(repeating: "A", count: 400))
        XCTAssertEqual(WatchMyStuffPublisher.boundedTitle(String(repeating: "A", count: 401)),
                       String(repeating: "A", count: 400) + "…")
        let title = String(repeating: "👨‍👩‍👧‍👦", count: 400)
        let clipped = WatchMyStuffPublisher.boundedTitle(title)
        XCTAssertLessThanOrEqual(clipped.utf8.count, WatchMyStuffSnapshot.maxTitleBytes)
        XCTAssertGreaterThan(clipped.count, 1)
    }
}
#endif
