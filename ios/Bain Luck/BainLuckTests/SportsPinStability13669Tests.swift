import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13669 — Pinning or unpinning a game on the Sports tab must not insert,
/// grow, shrink, or remove `Section("Pinned")` above `Live Now` under the
/// reader's finger (#13643 rule).
@MainActor
final class SportsPinStability13669Tests: XCTestCase {
    private nonisolated final class Client13669: SportsFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        init(feed: FeedResponse) { self.feed = feed }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#.utf8))
        }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(GroupedFeedResponse.self, from: Data(#"{"feed":[],"total":0,"limit":50,"offset":0}"#.utf8))
        }
    }

    private func makeSportsFeed() throws -> FeedResponse {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveCommence = iso.string(from: now.addingTimeInterval(-3600))
        let soonCommence = iso.string(from: now.addingTimeInterval(3600))
        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 95,
              "data": {
                "id": 9136691,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Boston Celtics",
                "away_team": "New York Knicks",
                "home_team_data": {"team_id": 2, "name": "Boston Celtics", "short_name": "Celtics", "abbreviation": "BOS", "primary_color": "#007A33"},
                "away_team_data": {"team_id": 18, "name": "New York Knicks", "short_name": "Knicks", "abbreviation": "NYK", "primary_color": "#006BB6"},
                "commence_time": "\(liveCommence)",
                "status": "live",
                "home_score": 81,
                "away_score": 76,
                "espn": {"period": "Q3", "clock": "5:12"},
                "current_odds": {"home_probability": 0.62, "away_probability": 0.38}
              }
            },
            {
              "type": "event",
              "score": 90,
              "data": {
                "id": 9136692,
                "sport": "icehockey_nhl",
                "sport_name": "NHL",
                "home_team": "Dallas Stars",
                "away_team": "Edmonton Oilers",
                "home_team_data": {"team_id": 25, "name": "Dallas Stars", "short_name": "Stars", "abbreviation": "DAL", "primary_color": "#006847"},
                "away_team_data": {"team_id": 22, "name": "Edmonton Oilers", "short_name": "Oilers", "abbreviation": "EDM", "primary_color": "#041E42"},
                "commence_time": "\(soonCommence)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.54, "away_probability": 0.46}
              }
            }
          ],
          "total": 2,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedResponse.self, from: Data(json.utf8))
    }

    func testSportsPinnedSnapshotFiltersOnlyCapturedIDs() throws {
        let feed = try makeSportsFeed()
        let empty = SportsPinnedSnapshot13669(eventIDs: [], futuresIDs: [])
        XCTAssertTrue(empty.pinnedItems(in: feed.items).isEmpty)

        let captured = SportsPinnedSnapshot13669(eventIDs: [9136691], futuresIDs: [])
        XCTAssertEqual(captured.pinnedItems(in: feed.items).map { $0.event?.id }, [9136691])
    }

    func testPinningOnSportsTabSavesImmediatelyAndMovesCardsZeroPoints() async throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13669_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let feed = try makeSportsFeed()
        let vm = FeedViewModel(client: Client13669(feed: feed), autoRefreshEnabled: false)
        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 2)

        let suiteName = "test-13669-pin-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()

        let view = FeedView(viewModel: vm)
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 852)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        func pumpAndSnapshot() -> UIImage {
            host.view.frame = bounds
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
        }

        let initialImg = pumpAndSnapshot()
        if let outDir, !outDir.isEmpty, let png = initialImg.pngData() {
            try png.write(to: URL(fileURLWithPath: "\(outDir)/after-initial.png"), options: .atomic)
        }
        let initialBoxes = try ocrBoxes(initialImg)
        let initialLiveY = try XCTUnwrap(initialBoxes.first { $0.text.contains("Live Now") }?.minY)
        let initialCelticsY = try XCTUnwrap(initialBoxes.first { $0.text.contains("Celtics") }?.minY)
        XCTAssertFalse(initialBoxes.contains { $0.text.contains("Pinned") })

        // Pin Celtics (9136691) while reading Sports tab
        pinManager.togglePin(type: "event", id: 9136691)
        XCTAssertTrue(pinManager.isPinned(type: "event", id: 9136691), "Pin must save immediately")

        let pinnedImg = pumpAndSnapshot()
        if let outDir, !outDir.isEmpty, let png = pinnedImg.pngData() {
            try png.write(to: URL(fileURLWithPath: "\(outDir)/after-pinned.png"), options: .atomic)
        }
        let pinnedBoxes = try ocrBoxes(pinnedImg)
        XCTAssertFalse(pinnedBoxes.contains { $0.text.contains("Pinned") }, "Pinned section must not insert above Live Now while reading")
        let afterLiveY = try XCTUnwrap(pinnedBoxes.first { $0.text.contains("Live Now") }?.minY)
        let afterCelticsY = try XCTUnwrap(pinnedBoxes.first { $0.text.contains("Celtics") }?.minY)

        XCTAssertLessThan(abs(afterLiveY - initialLiveY) * 852.0, 1.0, "Live Now section shifted under the reader")
        XCTAssertLessThan(abs(afterCelticsY - initialCelticsY) * 852.0, 1.0, "Celtics card shifted under the reader")
    }

    func testUnpinningInitiallyPinnedGameAlsoKeepsPageStillWhileReading() async throws {
        let feed = try makeSportsFeed()
        let vm = FeedViewModel(client: Client13669(feed: feed), autoRefreshEnabled: false)
        await vm.startLoad()

        let suiteName = "test-13669-unpin-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        pinManager.togglePin(type: "event", id: 9136691)
        XCTAssertTrue(pinManager.isPinned(type: "event", id: 9136691))
        let navCoordinator = NavigationCoordinator()

        let view = FeedView(viewModel: vm)
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 852)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        func pumpAndSnapshot() -> UIImage {
            host.view.frame = bounds
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
        }

        let beforeUnpin = try ocrBoxes(pumpAndSnapshot())
        XCTAssertTrue(beforeUnpin.contains { $0.text.contains("Pinned") })
        let beforeLiveY = try XCTUnwrap(beforeUnpin.first { $0.text.contains("Live Now") }?.minY)

        pinManager.togglePin(type: "event", id: 9136691)
        XCTAssertFalse(pinManager.isPinned(type: "event", id: 9136691))

        let afterUnpin = try ocrBoxes(pumpAndSnapshot())
        XCTAssertTrue(afterUnpin.contains { $0.text.contains("Pinned") }, "Pinned section stays in place until category switch or refresh")
        let afterLiveY = try XCTUnwrap(afterUnpin.first { $0.text.contains("Live Now") }?.minY)
        XCTAssertLessThan(abs(afterLiveY - beforeLiveY) * 852.0, 1.0, "Live Now shifted on unpin")
    }

    private func ocrBoxes(_ image: UIImage) throws -> [(text: String, minY: CGFloat)] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let s = obs.topCandidates(1).first?.string else { return nil }
            return (s, 1.0 - obs.boundingBox.maxY)
        }
    }
}
