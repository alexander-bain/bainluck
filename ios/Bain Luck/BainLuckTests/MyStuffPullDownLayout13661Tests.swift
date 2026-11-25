import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13661 — Pulling down on My Stuff must pull the entire scrollable body
/// smoothly under the `"My Stuff"` large title without trapping the Siri tip or
/// Manage Pins card above the scroll view or opening a split blank gap.
@MainActor
final class MyStuffPullDownLayout13661Tests: XCTestCase {

    private func myStuffViewSource() throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/MyStuffView.swift"), encoding: .utf8)
    }

    private func landingViewSource() throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/MyStuffLandingView295A.swift"), encoding: .utf8)
    }

    func testSiriTipAndManagePinsLiveInsideScrollingContainersInsteadOfPinnedOuterVStack() throws {
        let myStuff = try myStuffViewSource()
        let landing = try landingViewSource()

        XCTAssertTrue(myStuff.contains("NavigationStack(path: $path) {\n            Group {"),
                      "NavigationStack root in MyStuffView must not wrap a pinned header VStack above the ScrollView")
        XCTAssertTrue(myStuff.contains("managePinsHeaderRow13661"),
                      "Manage pins header row must stay mounted across fallback views")
        XCTAssertTrue(myStuff.contains(".accessibilityIdentifier(\"myStuffManagePins\")"))
        XCTAssertTrue(landing.contains("ScrollView {\n            LazyVStack(alignment: .leading, spacing: 20) {\n                SiriProbabilityTip12315(horizontalPadding: 0)"),
                      "MyStuffLandingBody295A must place SiriProbabilityTip12315 inside its scrolling LazyVStack")
    }

    private func samplePreloadedSnapshot() throws -> MyStuffLandingViewModel295A.PreloadedSnapshot {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveCommence = iso.string(from: now.addingTimeInterval(-3600))
        let soonCommence = iso.string(from: now.addingTimeInterval(3600))
        let json = """
        [
          {
            "id": 9136611,
            "sport": "americanfootball_nfl",
            "sport_name": "NFL",
            "home_team": "New England Patriots",
            "away_team": "Los Angeles Chargers",
            "home_team_data": {"team_id": 17, "name": "New England Patriots", "abbreviation": "NE", "primary_color": "#002244"},
            "away_team_data": {"team_id": 24, "name": "Los Angeles Chargers", "abbreviation": "LAC", "primary_color": "#0080C6"},
            "commence_time": "\(liveCommence)",
            "status": "live",
            "home_score": 17,
            "away_score": 18,
            "espn": {"period": "Q4", "clock": "3:12"},
            "current_odds": {"home_probability": 0.49, "away_probability": 0.51}
          },
          {
            "id": 9136612,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Boston Celtics",
            "away_team": "Washington Wizards",
            "home_team_data": {"team_id": 2, "name": "Boston Celtics", "abbreviation": "BOS", "primary_color": "#007A33"},
            "away_team_data": {"team_id": 27, "name": "Washington Wizards", "abbreviation": "WAS", "primary_color": "#002B5C"},
            "commence_time": "\(soonCommence)",
            "status": "live",
            "home_score": 115,
            "away_score": 104,
            "espn": {"period": "Q4", "clock": "1:05"},
            "current_odds": {"home_probability": 0.79, "away_probability": 0.21}
          }
        ]
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let events = try dec.decode([FeedEventData].self, from: Data(json.utf8))
        return MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: events.map { ($0, false) }
        )
    }

    func testPullingDownMyStuffKeepsSingleVerticalScrollViewAlignedWithoutNavOverlap() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13661_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let suite = "test-13661-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suite) }

        let followManager = FollowManager295A(defaults: defaults)
        _ = followManager.toggle(.team(slug: "boston-celtics", teamId: 2, name: "Boston Celtics", sportKey: "basketball_nba"))
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

        let view = MyStuffView(preloadedLandingForTest: try samplePreloadedSnapshot())
            .environment(\.followManager295A, followManager)
            .environmentObject(pinManager)
            .environmentObject(NavigationCoordinator())
            .environmentObject(AuthManager(restoreOnInit: false))
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(view, at: .large)
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

        func pump(_ loops: Int = 8) {
            host.view.frame = bounds
            for _ in 0..<loops {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
        }

        func capturePNG() -> UIImage {
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
        }

        pump(12)

        // Find the primary vertical UIScrollView inside MyStuffView.
        let scrollViews = collectViews(of: UIScrollView.self, in: window)
            .filter { $0.bounds.height > 400 }
        let mainScroll = try XCTUnwrap(scrollViews.first, "Expected vertical My Stuff ScrollView")
        // With the outer VStack removed, the ScrollView reaches the top of the NavigationStack
        // container instead of starting below an un-scrolled top header strip.
        let scrollFrameInWindow = mainScroll.convert(mainScroll.bounds, to: window)
        XCTAssertLessThanOrEqual(
            scrollFrameInWindow.minY,
            1.0,
            "My Stuff ScrollView must attach directly under NavigationStack (minY was \(scrollFrameInWindow.minY))"
        )

        let restingImg = capturePNG()
        let restingOCR = try ocrBoxes(restingImg)
        XCTAssertTrue(restingOCR.contains { $0.text.contains("My Stuff") }, "Missing My Stuff title")
        XCTAssertTrue(restingOCR.contains { $0.text.contains("Patriots") || $0.text.contains("Celtics") },
                      "Expected My Stuff cards in \(restingOCR.map(\.text))")

        // Simulate pulling down -95 pt past resting offset.
        let restingY = -mainScroll.adjustedContentInset.top
        mainScroll.setContentOffset(CGPoint(x: 0, y: restingY - 95), animated: false)
        pump(10)

        let pullImg = capturePNG()
        let pullOCR = try ocrBoxes(pullImg)
        let titleBox = try XCTUnwrap(pullOCR.first { $0.text == "My Stuff" } ?? pullOCR.first { $0.text.contains("My Stuff") },
                                   "Missing My Stuff nav title after pull-down")
        let cardOrChipMinY = pullOCR
            .filter { !$0.text.contains("My Stuff") && !$0.text.contains("Siri") }
            .map(\.minY)
            .min() ?? 1.0
        XCTAssertGreaterThan(
            cardOrChipMinY,
            titleBox.maxY,
            "Content overlapped My Stuff navigation title after -95 pt pull-down"
        )

        if let outDir, !outDir.isEmpty {
            if let restingData = restingImg.pngData() {
                try restingData.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13661-resting-390.png"))
            }
            if let pullData = pullImg.pngData() {
                try pullData.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13661-pulldown-390.png"))
            }

            // Replicate pre-fix layout bug (`VStack` holding non-scrolling tip bar outside ScrollView
            // pulled down -95 pt, creating split gap & colliding with `.large` nav bar).
            let preSnap = try samplePreloadedSnapshot()
            let preFixView = NavigationStack {
                VStack(spacing: 0) {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(DS.cardBg)
                        .frame(height: 54)
                        .overlay(
                            HStack {
                                Image(systemName: "waveform.circle.fill").foregroundStyle(.blue)
                                Text("Ask Bain Luck about a game").font(.subheadline.weight(.medium))
                                Spacer()
                            }.padding(.horizontal, 12)
                        )
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                    MyStuffLandingView295A(
                        landingVM: MyStuffLandingViewModel295A(preloaded: preSnap),
                        path: .constant(NavigationPath()),
                        onOpenDiscover: {},
                        onManagePins: {},
                        onRefresh: {}
                    )
                    .environment(\.followManager295A, followManager)
                    .environmentObject(pinManager)
                }
                .navigationTitle("My Stuff")
                .navigationBarTitleDisplayMode(.large)
            }
            let preHost = hostForMeasurement(preFixView, at: .large)
            preHost.overrideUserInterfaceStyle = .light
            preHost.traitOverrides.horizontalSizeClass = .compact
            window.rootViewController = preHost
            preHost.view.frame = bounds
            for _ in 0..<8 {
                preHost.view.setNeedsLayout()
                preHost.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
            if let preScroll = collectViews(of: UIScrollView.self, in: window).filter({ $0.bounds.height > 400 }).first {
                preScroll.setContentOffset(CGPoint(x: 0, y: -preScroll.adjustedContentInset.top - 95), animated: false)
                for _ in 0..<8 {
                    preHost.view.setNeedsLayout()
                    preHost.view.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.03))
                }
            }
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let preImg = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = preHost.view.drawHierarchy(in: preHost.view.bounds, afterScreenUpdates: true)
            }
            if let d = preImg.pngData() {
                try d.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-13661-pulldown-390.png"))
            }
            window.rootViewController = host
        }
    }

    private func collectViews<T: UIView>(of type: T.Type, in root: UIView) -> [T] {
        var result: [T] = []
        if let match = root as? T { result.append(match) }
        for sub in root.subviews {
            result.append(contentsOf: collectViews(of: type, in: sub))
        }
        return result
    }

    private func ocrBoxes(_ image: UIImage) throws -> [(text: String, minY: CGFloat, maxY: CGFloat)] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let s = obs.topCandidates(1).first?.string else { return nil }
            let minY = 1.0 - obs.boundingBox.maxY
            let maxY = 1.0 - obs.boundingBox.minY
            return (s, minY, maxY)
        }
    }
}
