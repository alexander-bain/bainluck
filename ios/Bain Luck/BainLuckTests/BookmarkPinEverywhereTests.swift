import Darwin
import SwiftUI
import XCTest
@testable import Bain_Luck

final class BookmarkPinEverywhereTests: XCTestCase {

    override class func setUp() {
        super.setUp()
        setAccessibilityAutomation(true)
    }

    override class func tearDown() {
        setAccessibilityAutomation(false)
        super.tearDown()
    }

    private static func setAccessibilityAutomation(_ enabled: Bool) {
        #if os(iOS)
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
        #endif
    }

    private var iosRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private func source(_ relativePath: String) throws -> String {
        let url = iosRoot.appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    func testPinButtonDrawsBookmarkEverywhere() throws {
        let pinButton = try source("Bain Luck/Components/PinButton.swift")
        XCTAssertTrue(pinButton.contains("\"bookmark.fill\" : \"bookmark\""))
        XCTAssertFalse(pinButton.contains("pushpin"))
        XCTAssertFalse(pinButton.contains("\"star"))
    }

    func testDetailPagesAndCardsWireSharedBookmarkPinButton() throws {
        let eventPage = try source("Bain Luck/Views/EventDetailView.swift")
        let marketPage = try source("Bain Luck/Views/FuturesDetailView.swift")
        let sportsCard = try source("Bain Luck/Components/EventCardView.swift")
        let browseFuturesCard = try source("Bain Luck/Components/FuturesCardView.swift")
        let discoverEventCard = try source("Bain Luck/Components/DiscoverEventCard.swift")
        let discoverFuturesCard = try source("Bain Luck/Components/DiscoverFuturesCard.swift")
        let welcome = try source("Bain Luck/Views/WelcomeView.swift")

        XCTAssertTrue(eventPage.contains("PinButton(type: \"event\", id: eventId)"))
        XCTAssertTrue(marketPage.contains("PinButton(type: \"future\", id: marketId)"))
        XCTAssertTrue(sportsCard.contains("PinButton(type: \"event\", id: event.id, compact: true)"))
        XCTAssertTrue(browseFuturesCard.contains("PinButton(type: \"future\", id: futures.id, compact: true)"))
        XCTAssertTrue(discoverEventCard.contains("PinButton(type: \"event\", id: event.id)"))
        XCTAssertTrue(discoverFuturesCard.contains("PinButton(type: \"future\", id: data.id)"))
        XCTAssertTrue(welcome.contains("Image(systemName: \"bookmark.fill\")"))
        XCTAssertFalse(welcome.contains("Image(systemName: \"star.fill\")"))
    }

    func testWatchAndWidgetUseBookmarkIconsNotBarsOrCheckmarks() throws {
        let watchComplication = try source("BainLuckWatch Watch App/WatchSavedComplicationContent.swift")
        let watchPinsHome = try source("BainLuckWatch Watch App/WatchPinnedHomeView12640.swift")
        let watchSelected = try source("BainLuckWatch Watch App/WatchSelectedGameView.swift")
        let savedWidget = try source("BainLuckWidget/SavedItemWidget10875.swift")
        let savedControl = try source("BainLuckWidget/SavedItemControl12305.swift")

        XCTAssertEqual(
            watchComplication.components(separatedBy: "Image(systemName: \"bookmark\")").count - 1,
            3,
            "All three Watch complication launcher/fallback slots must draw bookmark"
        )
        XCTAssertFalse(watchComplication.contains("chart.bar.fill"))

        XCTAssertEqual(
            watchPinsHome.components(separatedBy: "Image(systemName: \"bookmark.fill\")").count - 1,
            2,
            "Both active Watch pin cards (game and market) must draw bookmark.fill"
        )

        XCTAssertTrue(watchSelected.contains("systemImage: \"bookmark.fill\""))
        XCTAssertTrue(savedWidget.contains("Image(systemName: \"bookmark\")"))
        XCTAssertTrue(savedControl.contains("systemImage: \"bookmark.fill\""))
    }

    #if os(iOS)
    @MainActor
    func testExport390RendersIfRequested() throws {
        guard let dirPath = ProcessInfo.processInfo.environment["BAINLUCK_RENDER_BOOKMARK_PINS_DIR"],
              !dirPath.isEmpty else {
            return
        }
        let outDir = URL(fileURLWithPath: dirPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let defaults = UserDefaults(suiteName: "BookmarkPinEverywhereTests.\(UUID().uuidString)")!
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [7002], futures: [8002]) },
            serverSync: { _, _, _ in }
        )
        pins.pinnedEventIDs = [7002]
        pins.pinnedFuturesIDs = [8002]

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let unpinnedGame = try decoder.decode(FeedEventData.self, from: Data("""
        {
          "id": 7001,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "away_team_data": {"abbreviation": "PIT", "primary_color": "#FFB612"},
          "home_team_data": {"abbreviation": "CIN", "primary_color": "#FB4F14"},
          "current_odds": {"away_probability": 0.34, "home_probability": 0.66, "away_rendered_percent": 34, "home_rendered_percent": 66}
        }
        """.utf8))

        let pinnedGame = try decoder.decode(FeedEventData.self, from: Data("""
        {
          "id": 7002,
          "sport": "basketball_nba",
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "commence_time": "2026-11-14T00:30:00Z",
          "status": "live",
          "home_score": 100,
          "away_score": 98,
          "espn": {"period": "Q4", "game_clock": "02:14"},
          "away_team_data": {"abbreviation": "BOS", "primary_color": "#007A33"},
          "home_team_data": {"abbreviation": "PHI", "primary_color": "#006BB6"},
          "prematch_odds": {"away_probability": 0.49, "home_probability": 0.51},
          "current_odds": {"away_probability": 0.412, "home_probability": 0.588, "away_rendered_percent": 41, "home_rendered_percent": 59}
        }
        """.utf8))

        let pinnedMarket = try decoder.decode(FeedFuturesData.self, from: Data("""
        {
          "id": 8002,
          "name": "Next Federal Reserve Chair",
          "sport": null,
          "sport_name": "Economics",
          "llm_sport_category": "economics",
          "source": "kalshi",
          "source_count": 2,
          "status": "open",
          "confidence_tier": "high",
          "top_outcomes": [
            {"id": 1, "name": "Kevin Warsh", "probability": 0.44, "rendered_percent": 44},
            {"id": 2, "name": "Scott Bessent", "probability": 0.31, "rendered_percent": 31},
            {"id": 3, "name": "Christopher Waller", "probability": 0.16, "rendered_percent": 16}
          ]
        }
        """.utf8))

        func renderSheet<V: View>(_ content: V, fileName: String) throws {
            let canvas = content
                .padding(16)
                .frame(width: 390)
                .background(Color(white: 0.965))
                .environmentObject(pins)
                .environment(\.colorScheme, .light)
            let renderer = rendererForMeasurement(canvas)
            renderer.scale = 3.0
            renderer.proposedSize = ProposedViewSize(width: 390, height: nil)
            let image = try XCTUnwrap(renderer.uiImage)
            try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent(fileName))
        }

        try renderSheet(
            VStack(alignment: .leading, spacing: 14) {
                Text("DISCOVER GAME CARD · UNPINNED BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                NativeEventDiscoverCard(
                    event: unpinnedGame,
                    feedContext: "AFC North opener in Pittsburgh",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )

                Text("DISCOVER GAME CARD · PINNED BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                NativeEventDiscoverCard(
                    event: pinnedGame,
                    feedContext: "76ers jumped 8 points in the fourth quarter",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            },
            fileName: "overnight1-discover-game-bookmark-390.png"
        )

        try renderSheet(
            VStack(alignment: .leading, spacing: 14) {
                Text("DISCOVER MARKET CARD · PINNED BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                NativeFuturesDiscoverCard(
                    data: pinnedMarket,
                    feedContext: "Warsh leads ahead of Senate confirmation talks",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )

                Text("SPORTS / MY STUFF GAME CARD · PINNED BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                EventCardView(event: pinnedGame, reason: nil)
                    .padding(12)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
            },
            fileName: "overnight1-market-and-sports-bookmark-390.png"
        )

        try renderSheet(
            VStack(alignment: .leading, spacing: 14) {
                Text("GAME & MARKET DETAIL TOOLBARS · BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                HStack(spacing: 12) {
                    HStack {
                        Text("Game Page")
                            .font(.subheadline.weight(.semibold))
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                        PinButton(type: "event", id: 7001, compact: true)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))

                    HStack {
                        Text("Market Page")
                            .font(.subheadline.weight(.semibold))
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                        PinButton(type: "future", id: 8002, compact: true)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
                }

                Text("APPLE WATCH COMPLICATION SLOTS & PINS HOME · BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 14) {
                        HStack(spacing: 8) {
                            Image(systemName: "bookmark").font(.title3).foregroundStyle(.white)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("Your game").font(.footnote.weight(.semibold)).foregroundStyle(.white)
                                Text("Open Bain Luck").font(.caption2).foregroundStyle(.white.opacity(0.7))
                            }
                        }
                        .padding(10)
                        .background(Color.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))

                        ZStack {
                            Circle().fill(Color.white.opacity(0.12)).frame(width: 40, height: 40)
                            Image(systemName: "bookmark").font(.system(size: 18)).foregroundStyle(.white)
                        }

                        ZStack {
                            RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(0.12)).frame(width: 40, height: 40)
                            Image(systemName: "bookmark").font(.system(size: 18)).foregroundStyle(.white)
                        }
                    }

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text("Live · Q4 02:14")
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.cyan)
                            Spacer(minLength: 4)
                            Image(systemName: "bookmark.fill")
                                .font(.caption2)
                                .foregroundStyle(.orange)
                        }
                        Text("BOS at PHI · 98–100")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(.white)
                        Text("PHI 59%")
                            .font(.title3.bold().monospacedDigit())
                            .foregroundStyle(.cyan)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
                }
                .padding(14)
                .background(Color.black, in: RoundedRectangle(cornerRadius: 16))

                Text("HOME SCREEN SAVED WIDGET EMPTY STATE · BOOKMARK")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 4) {
                    Image(systemName: "bookmark").foregroundStyle(.secondary)
                    Text("Choose a pinned game or market")
                        .font(.footnote.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Pin in Bain Luck, then edit widget")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(14)
                .frame(width: 170, alignment: .topLeading)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 20))
            },
            fileName: "overnight1-surfaces-bookmark-390.png"
        )
    }

    private func findAccessibilityControl(exactLabel target: String, in root: NSObject) -> NSObject? {
        if root.accessibilityLabel == target { return root }
        var children: [NSObject] = []
        if let elements = root.accessibilityElements as? [NSObject] { children += elements }
        let count = root.accessibilityElementCount()
        if count != NSNotFound, count > 0 {
            children += (0..<count).compactMap { root.accessibilityElement(at: $0) as? NSObject }
        }
        if let view = root as? UIView { children += view.subviews }
        for child in children {
            if let found = findAccessibilityControl(exactLabel: target, in: child) { return found }
        }
        return nil
    }

    @MainActor
    private func mountCardOnActiveWindow<V: View>(
        _ view: V,
        pinManager: PinManager
    ) async throws -> (UIViewController, UIWindow, UIWindow?) {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first
        let previous = scene?.windows.first { $0.isKeyWindow }
        let host = hostForMeasurement(
            view
                .frame(width: 390)
                .environmentObject(pinManager)
                .environment(\.colorScheme, .light)
        )
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = scene.map(UIWindow.init(windowScene:)) ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        return (host, window, previous)
    }

    @MainActor
    private func waitForCondition(
        on host: UIViewController,
        timeout: TimeInterval = 3,
        condition: () -> Bool
    ) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            if condition() { return true }
            try? await Task.sleep(nanoseconds: 20_000_000)
        } while Date() < deadline
        return condition()
    }

    @MainActor
    func testRenderedDiscoverEventCardExposesAndTogglesBookmarkPin() async throws {
        let defaults = UserDefaults(suiteName: "BookmarkPinEventBehavioral.\(UUID().uuidString)")!
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let game = try decoder.decode(FeedEventData.self, from: Data("""
        {
          "id": 77101,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "away_team_data": {"abbreviation": "PIT", "primary_color": "#FFB612"},
          "home_team_data": {"abbreviation": "CIN", "primary_color": "#FB4F14"},
          "current_odds": {"away_probability": 0.34, "home_probability": 0.66, "away_rendered_percent": 34, "home_rendered_percent": 66}
        }
        """.utf8))

        var navRoutesCount = 0
        let navBinding = Binding<NavigationPath>(
            get: { NavigationPath() },
            set: { path in navRoutesCount = path.count }
        )

        let (host, window, previous) = try await mountCardOnActiveWindow(
            NativeEventDiscoverCard(
                event: game,
                feedContext: "AFC North opener in Pittsburgh",
                expandedContext: nil,
                navigationPath: navBinding
            ),
            pinManager: pins
        )
        defer {
            window.isHidden = true
            previous?.makeKey()
        }

        var pinControl: NSObject?
        let foundUnpinned = await waitForCondition(on: host) {
            pinControl = self.findAccessibilityControl(exactLabel: "Pin", in: host.view)
            return pinControl != nil
        }
        XCTAssertTrue(foundUnpinned, "Discover game card must render an interactive Pin bookmark control")
        XCTAssertFalse(pins.isPinned(type: "event", id: 77101))
        XCTAssertNil(findAccessibilityControl(exactLabel: "Unpin", in: host.view))

        XCTAssertTrue(try XCTUnwrap(pinControl).accessibilityActivate(), "Pin control accepts tap activation")
        let flippedToPinned = await waitForCondition(on: host) {
            pins.isPinned(type: "event", id: 77101)
                && self.findAccessibilityControl(exactLabel: "Unpin", in: host.view) != nil
        }
        XCTAssertTrue(flippedToPinned, "Tapping Pin on Discover game card pins the event and flips accessibility label to Unpin")
        XCTAssertEqual(pins.pinnedEventIDs, [77101])
        XCTAssertEqual(pins.orderedEventIDs, [77101])
        XCTAssertEqual(navRoutesCount, 0, "Tapping Pin must not navigate into the event detail page")

        let unpinControl = try XCTUnwrap(findAccessibilityControl(exactLabel: "Unpin", in: host.view))
        XCTAssertTrue(unpinControl.accessibilityActivate(), "Unpin control accepts tap activation")
        let flippedBackToUnpinned = await waitForCondition(on: host) {
            !pins.isPinned(type: "event", id: 77101)
                && self.findAccessibilityControl(exactLabel: "Pin", in: host.view) != nil
        }
        XCTAssertTrue(flippedBackToUnpinned, "Tapping Unpin removes the event pin and restores Pin label")
        XCTAssertTrue(pins.pinnedEventIDs.isEmpty)
        XCTAssertTrue(pins.orderedEventIDs.isEmpty)
    }

    @MainActor
    func testRenderedDiscoverFuturesCardExposesAndTogglesBookmarkPin() async throws {
        let defaults = UserDefaults(suiteName: "BookmarkPinFuturesBehavioral.\(UUID().uuidString)")!
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let market = try decoder.decode(FeedFuturesData.self, from: Data("""
        {
          "id": 88202,
          "name": "Next Federal Reserve Chair",
          "sport": null,
          "sport_name": "Economics",
          "llm_sport_category": "economics",
          "source": "kalshi",
          "source_count": 2,
          "status": "open",
          "confidence_tier": "high",
          "top_outcomes": [
            {"id": 1, "name": "Kevin Warsh", "probability": 0.44, "rendered_percent": 44},
            {"id": 2, "name": "Scott Bessent", "probability": 0.31, "rendered_percent": 31}
          ]
        }
        """.utf8))

        var navRoutesCount = 0
        let navBinding = Binding<NavigationPath>(
            get: { NavigationPath() },
            set: { path in navRoutesCount = path.count }
        )

        let (host, window, previous) = try await mountCardOnActiveWindow(
            NativeFuturesDiscoverCard(
                data: market,
                feedContext: "Warsh leads ahead of confirmation talks",
                expandedContext: nil,
                navigationPath: navBinding
            ),
            pinManager: pins
        )
        defer {
            window.isHidden = true
            previous?.makeKey()
        }

        var pinControl: NSObject?
        let foundUnpinned = await waitForCondition(on: host) {
            pinControl = self.findAccessibilityControl(exactLabel: "Pin", in: host.view)
            return pinControl != nil
        }
        XCTAssertTrue(foundUnpinned, "Discover market card must render an interactive Pin bookmark control")
        XCTAssertFalse(pins.isPinned(type: "future", id: 88202))

        XCTAssertTrue(try XCTUnwrap(pinControl).accessibilityActivate(), "Market Pin control accepts tap activation")
        let flippedToPinned = await waitForCondition(on: host) {
            pins.isPinned(type: "future", id: 88202)
                && self.findAccessibilityControl(exactLabel: "Unpin", in: host.view) != nil
        }
        XCTAssertTrue(flippedToPinned, "Tapping Pin on Discover market card pins the market and flips label to Unpin")
        XCTAssertEqual(pins.pinnedFuturesIDs, [88202])
        XCTAssertEqual(pins.orderedFuturesIDs, [88202])
        XCTAssertEqual(navRoutesCount, 0, "Tapping Pin must not navigate into the market detail page")

        let unpinControl = try XCTUnwrap(findAccessibilityControl(exactLabel: "Unpin", in: host.view))
        XCTAssertTrue(unpinControl.accessibilityActivate(), "Market Unpin control accepts tap activation")
        let flippedBackToUnpinned = await waitForCondition(on: host) {
            !pins.isPinned(type: "future", id: 88202)
                && self.findAccessibilityControl(exactLabel: "Pin", in: host.view) != nil
        }
        XCTAssertTrue(flippedBackToUnpinned, "Tapping Unpin removes the market pin and restores Pin label")
        XCTAssertTrue(pins.pinnedFuturesIDs.isEmpty)
        XCTAssertTrue(pins.orderedFuturesIDs.isEmpty)
    }
    #endif
}
