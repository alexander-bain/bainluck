import XCTest
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
@testable import Bain_Luck

/// Guard + visual proof for #13832:
/// 1. Discover futures outcome rows ("Oklahoma City Thunder") never truncate at 390, 320, or AX5.
/// 2. Preferences "Your Interests" rows ("College Football", "College Basketball") never break mid-word at 320, 390, or AX5.
/// 3. NativeGroupCard header ("AI & TECH MILESTONES") never breaks mid-word at AX5 (320 or 390).
/// 4. MovementBadge scales with Dynamic Type at AX5 instead of staying frozen at 7pt/10pt.
@MainActor
final class DiscoverAndPreferencesCutoffs13832Tests: XCTestCase {

    // MARK: - Source contracts

    private static var iosRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }

    func testMovementBadgeUsesScaledMetricInsteadOfFrozenPointSizes() throws {
        let src = try String(
            contentsOf: Self.iosRoot.appendingPathComponent("Views/DiscoverView.swift"),
            encoding: .utf8
        )
        let parts = src.components(separatedBy: "struct MovementBadge: View {")
        XCTAssertEqual(parts.count, 2)
        let body = String(parts[1].prefix(900))
        XCTAssertTrue(body.contains("@ScaledMetric"), "MovementBadge must scale with Dynamic Type via @ScaledMetric")
        XCTAssertFalse(body.contains(".font(.system(size: 7"), "MovementBadge must not hardcode frozen 7pt arrow")
        XCTAssertFalse(body.contains(".font(.system(size: 10"), "MovementBadge must not hardcode frozen 10pt text")
    }

    func testFuturesCardOutcomeRowsMeasureGeometrySynchronouslyAndStackAtAccessibilitySizes() throws {
        let src = try String(
            contentsOf: Self.iosRoot.appendingPathComponent("Components/DiscoverFuturesCard.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(src.contains(".onGeometryChange(for: Double.self)"))
        XCTAssertTrue(src.contains("if dynamicTypeSize.isAccessibilitySize"))
        XCTAssertTrue(src.contains("maxWidth: .infinity"))
    }

    // MARK: - Rendered OCR + Sheet Captures

    #if canImport(UIKit)

    func testMovementBadgeGrowsAtAX5() throws {
        let auth = AuthManager(restoreOnInit: false)
        let largeSize = hostSize(
            MovementBadge(movement: 0.04).padding(4).environmentObject(auth),
            width: 200,
            colorScheme: .light,
            dynamicTypeSize: .large
        )
        let ax5Size = hostSize(
            MovementBadge(movement: 0.04).padding(4).environmentObject(auth),
            width: 200,
            colorScheme: .light,
            dynamicTypeSize: .accessibility5
        )
        XCTAssertGreaterThan(ax5Size.width, largeSize.width + 8, "MovementBadge width should scale up at AX5")
        XCTAssertGreaterThan(ax5Size.height, largeSize.height + 4, "MovementBadge height should scale up at AX5")
    }

    func testCutoffsResolvedAt320And390AndAX5LightAndDarkAndEmitSheetPanels() async throws {
        let outDir = URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["BAINLUCK_RENDER_13832_DIR"]
                ?? "/tmp/bainluck-renders-13832"
        )
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let auth = AuthManager(restoreOnInit: false)
        let pins = PinManager(defaults: .standard, allowLegacyGuestPins: false)

        // 1. NativeFuturesDiscoverCard: "NBA Championship Winner 2026–27?" with "Oklahoma City Thunder" 34%
        let futuresJSON = """
        {
          "type": "futures",
          "score": 96,
          "data": {
            "id": 86833,
            "name": "NBA Championship Winner 2026–27?",
            "category": "sports",
            "llm_sport_category": "basketball",
            "sport_name": "Basketball",
            "source": "kalshi",
            "status": "open",
            "outcome_count": 30,
            "top_outcomes": [
              {"id": 1, "name": "Oklahoma City Thunder", "probability": 0.34, "rank": 1, "movement": 0.04},
              {"id": 2, "name": "Boston Celtics", "probability": 0.28, "rank": 2, "movement": -0.02},
              {"id": 3, "name": "Cleveland Cavaliers", "probability": 0.14, "rank": 3, "movement": 0.01}
            ]
          }
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let futuresItem = try decoder.decode(FeedItem.self, from: Data(futuresJSON.utf8))
        let futuresData = try XCTUnwrap(futuresItem.futures)

        let futuresVariants: [(String, CGFloat, ColorScheme, DynamicTypeSize, Bool)] = [
            ("01-futures-390-light-frame1", 390, .light, .large, false),
            ("02-futures-390-dark", 390, .dark, .large, true),
            ("03-futures-320-light", 320, .light, .large, true),
            ("04-futures-390-ax5-light", 390, .light, .accessibility5, true),
            ("05-futures-320-ax5-dark", 320, .dark, .accessibility5, true),
        ]

        for (name, width, scheme, dt, settle) in futuresVariants {
            let card = VStack(spacing: 0) {
                NativeFuturesDiscoverCard(
                    data: futuresData,
                    feedContext: "Oklahoma City leads entering December.",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
            .padding(16)
            .background(Color(scheme == .dark ? .black : .systemGroupedBackground))
            .environmentObject(auth)
            .environmentObject(pins)
            .environment(\.colorScheme, scheme)

            let (img, fitted) = try await captureFitted(
                card,
                width: width,
                colorScheme: scheme,
                dynamicTypeSize: dt,
                settle: settle
            )
            XCTAssertLessThanOrEqual(fitted.width, width + 1.0, "\(name) overflowed width \(width)")
            let ocr = try recognizeText(in: img)
            XCTAssertFalse(ocr.contains("Thun…"), "\(name) truncated Oklahoma City Thunder: \(ocr)")
            XCTAssertFalse(ocr.contains("Okla-"), "\(name) hyphen-broke Oklahoma: \(ocr)")
            XCTAssertFalse(ocr.contains("Bos-"), "\(name) hyphen-broke Boston: \(ocr)")
            XCTAssertFalse(ocr.contains("BASKET-"), "\(name) hyphen-broke BASKETBALL chip: \(ocr)")
            XCTAssertFalse(ocr.contains("…"), "\(name) truncated text with ellipsis: \(ocr)")
            XCTAssertTrue(ocr.contains("BASKETBALL"), "\(name) missing whole category chip BASKETBALL: \(ocr)")
            XCTAssertTrue(ocr.contains("December"), "\(name) truncated context line under title: \(ocr)")
            XCTAssertTrue(ocr.contains("Oklahoma"), "\(name) missing whole word Oklahoma: \(ocr)")
            XCTAssertTrue(ocr.contains("Thunder"), "\(name) missing whole word Thunder: \(ocr)")
            XCTAssertTrue(ocr.contains("Boston") && ocr.contains("Celtics"), "\(name) missing whole Boston Celtics: \(ocr)")
            try savePNG(img, to: outDir.appendingPathComponent("\(name).png"))
        }

        // 2. PreferencesView "Your Interests" ("College Football", "College Basketball", "Entertainment")
        let prefsJSON = """
        {
          "home_location": null,
          "sport_affinities": {
            "nfl": 1.0,
            "college_football": 0.9,
            "nba": 0.7,
            "college_basketball": 0.6,
            "entertainment": 0.5
          },
          "onboarding_completed": true,
          "favorites": [],
          "push_preferences": {
            "daily_challenge": true,
            "big_moves": true,
            "morning_digest": false
          }
        }
        """
        let prefs = try decoder.decode(PreferencesResponse.self, from: Data(prefsJSON.utf8))
        let prefsVariants: [(String, CGFloat, ColorScheme, DynamicTypeSize, String, [String])] = [
            ("06-prefs-390-light", 390, .light, .large, "Your Interests", ["College Football", "College Basketball"]),
            ("07-prefs-320-light", 320, .light, .large, "Your Interests", ["College Football", "College Basketball"]),
            ("07b-prefs-320-beyond-light", 320, .light, .large, "Beyond Sports", ["Entertainment"]),
            ("08-prefs-390-ax5-light", 390, .light, .accessibility5, "Your Interests", ["College Football"]),
            ("09-prefs-390-ax5-dark", 390, .dark, .accessibility5, "Your Interests", ["College Football"]),
            ("10-prefs-320-ax5-light", 320, .light, .accessibility5, "Your Interests", ["College Football"]),
        ]

        for (name, width, scheme, dt, anchorLabel, expectedWholeNames) in prefsVariants {
            let img = try await capturePreferencesInterests(
                prefs: prefs,
                width: width,
                colorScheme: scheme,
                dynamicTypeSize: dt,
                anchorText: anchorLabel,
                auth: auth
            )
            let ocr = try recognizeText(in: img)
            XCTAssertFalse(ocr.contains("Col-"), "\(name) hyphen-broke College: \(ocr)")
            XCTAssertFalse(ocr.contains("Basket-"), "\(name) hyphen-broke Basketball: \(ocr)")
            XCTAssertFalse(ocr.contains("Foot-"), "\(name) hyphen-broke Football: \(ocr)")
            XCTAssertFalse(ocr.contains("Enter-"), "\(name) hyphen-broke Entertainment: \(ocr)")
            XCTAssertFalse(ocr.contains("…"), "\(name) truncated text: \(ocr)")
            for whole in expectedWholeNames {
                for word in whole.split(separator: " ").map(String.init) {
                    XCTAssertTrue(ocr.contains(word), "\(name) missing whole word '\(word)' from '\(whole)': \(ocr)")
                }
            }
            try savePNG(img, to: outDir.appendingPathComponent("\(name).png"))
        }

        // 3. NativeGroupCard header ("AI & TECH MILESTONES") + scaled MovementBadge under percent
        let groupItemsJSON = """
        [
          {
            "type": "futures",
            "score": 90,
            "data": {
              "id": 99101,
              "name": "Will OpenAI IPO before 2027?",
              "category": "tech",
              "llm_sport_category": "tech",
              "source": "polymarket",
              "status": "open",
              "outcome_count": 2,
              "top_outcomes": [
                {"id": 1, "name": "Yes", "probability": 0.42, "rank": 1, "movement": 0.03},
                {"id": 2, "name": "No", "probability": 0.58, "rank": 2, "movement": -0.03}
              ]
            }
          },
          {
            "type": "futures",
            "score": 88,
            "data": {
              "id": 99102,
              "name": "Will Anthropic reach a $100B valuation?",
              "category": "tech",
              "llm_sport_category": "tech",
              "source": "kalshi",
              "status": "open",
              "outcome_count": 2,
              "top_outcomes": [
                {"id": 3, "name": "Yes", "probability": 0.78, "rank": 1, "movement": -0.02},
                {"id": 4, "name": "No", "probability": 0.22, "rank": 2, "movement": 0.02}
              ]
            }
          },
          {
            "type": "futures",
            "score": 84,
            "data": {
              "id": 99103,
              "name": "Next major foundation model leader in 2026?",
              "category": "tech",
              "llm_sport_category": "tech",
              "source": "polymarket",
              "status": "open",
              "outcome_count": 4,
              "top_outcomes": [
                {"id": 5, "name": "Google Gemini", "probability": 0.56, "rank": 1, "movement": 0.04}
              ]
            }
          }
        ]
        """
        let groupItems = try decoder.decode([FeedItem].self, from: Data(groupItemsJSON.utf8))
        let groupVariants: [(String, CGFloat, ColorScheme, DynamicTypeSize)] = [
            ("11-group-390-light", 390, .light, .large),
            ("12-group-320-light", 320, .light, .large),
            ("13-group-390-ax5-light", 390, .light, .accessibility5),
            ("14-group-390-ax5-dark", 390, .dark, .accessibility5),
            ("15-group-320-ax5-dark", 320, .dark, .accessibility5),
        ]

        for (name, width, scheme, dt) in groupVariants {
            let groupCard = VStack(spacing: 0) {
                NativeGroupCard(
                    title: "AI & Tech Milestones",
                    items: groupItems,
                    kind: "theme",
                    navigationPath: .constant(NavigationPath())
                )
            }
            .padding(16)
            .background(Color(scheme == .dark ? .black : .systemGroupedBackground))
            .environmentObject(auth)
            .environmentObject(pins)
            .environment(\.colorScheme, scheme)

            let (img, fitted) = try await captureFitted(
                groupCard,
                width: width,
                colorScheme: scheme,
                dynamicTypeSize: dt,
                settle: true
            )
            XCTAssertLessThanOrEqual(fitted.width, width + 1.0, "\(name) overflowed width \(width)")
            let ocr = try recognizeText(in: img)
            XCTAssertFalse(ocr.contains("MILE-"), "\(name) hyphen-broke MILESTONES: \(ocr)")
            XCTAssertFalse(ocr.contains("…"), "\(name) truncated text: \(ocr)")
            XCTAssertTrue(ocr.contains("MILESTONES"), "\(name) missing whole MILESTONES: \(ocr)")
            XCTAssertTrue(ocr.contains("3%"), "\(name) missing MovementBadge 3%: \(ocr)")
            try savePNG(img, to: outDir.appendingPathComponent("\(name).png"))
        }
    }

    // MARK: - Hosting helpers

    private func hostSize<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) -> CGSize {
        let wrapped = view.environment(\.colorScheme, colorScheme)
        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        host.view.traitOverrides.preferredContentSizeCategory = uiCategory(for: dynamicTypeSize)
        return host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingCompressedSize.height))
    }

    private func captureFitted<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        settle: Bool
    ) async throws -> (UIImage, CGSize) {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: width, alignment: .topLeading)
            .ignoresSafeArea()
            .environment(\.colorScheme, colorScheme)
            .environment(\.horizontalSizeClass, .compact)
        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.traitOverrides.preferredContentSizeCategory = uiCategory(for: dynamicTypeSize)
        let measured = host.sizeThatFits(
            in: CGSize(width: width, height: 2400)
        )
        let height = min(2400, max(80, ceil(measured.height)))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        if settle {
            for _ in 0..<6 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try? await Task.sleep(nanoseconds: 35_000_000)
                let nextSize = host.sizeThatFits(
                    in: CGSize(width: width, height: 2400)
                )
                let nextHeight = min(2400, max(80, ceil(nextSize.height)))
                if abs(nextHeight - host.view.frame.height) > 1 {
                    host.view.frame = CGRect(x: 0, y: 0, width: width, height: nextHeight)
                    window.frame = host.view.frame
                }
            }
        } else {
            try? await Task.sleep(nanoseconds: 10_000_000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
        }

        let finalSize = host.view.bounds.size
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            let bg: UIColor = colorScheme == .dark ? .black : .systemGroupedBackground
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
        return (image, finalSize)
    }

    private func capturePreferencesInterests(
        prefs: PreferencesResponse,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        anchorText: String,
        auth: AuthManager
    ) async throws -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let viewportHeight: CGFloat = dynamicTypeSize.isAccessibilitySize ? 980 : 620
        let wrapped = NavigationStack {
            PreferencesView(loadedPrefsForTest: prefs)
                .frame(maxWidth: width, maxHeight: .infinity)
        }
        .environmentObject(auth)
        .environment(\.colorScheme, colorScheme)
        .environment(\.horizontalSizeClass, .compact)
        .frame(width: width, height: viewportHeight)

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.traitOverrides.preferredContentSizeCategory = uiCategory(for: dynamicTypeSize)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: viewportHeight)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 35_000_000)
        }

        if let scrollView = findScrollView(in: host.view) {
            let maxOffset = max(0, scrollView.contentSize.height - scrollView.bounds.height)
            let desiredOffset: CGFloat
            if let windowFrame = findAccessibilityElementFrame(containing: anchorText, in: scrollView) {
                let frameInScroll = scrollView.convert(windowFrame, from: nil)
                let topInset = scrollView.adjustedContentInset.top
                desiredOffset = max(0, min(maxOffset, frameInScroll.minY - topInset - 14))
            } else {
                let fallbackFraction: CGFloat = anchorText == "Beyond Sports" ? 0.55 : (dynamicTypeSize.isAccessibilitySize ? 0.055 : 0.11)
                desiredOffset = min(maxOffset, maxOffset * fallbackFraction)
            }
            scrollView.setContentOffset(CGPoint(x: 0, y: desiredOffset), animated: false)
            for _ in 0..<4 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try? await Task.sleep(nanoseconds: 30_000_000)
            }
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            let bg: UIColor = colorScheme == .dark ? .black : .systemGroupedBackground
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func findAccessibilityElementFrame(containing needle: String, in root: Any) -> CGRect? {
        if let elem = root as? NSObject {
            if let label = elem.accessibilityLabel,
               label.localizedCaseInsensitiveContains(needle),
               elem.accessibilityFrame != .zero {
                return elem.accessibilityFrame
            }
            let count = elem.accessibilityElementCount()
            if count != NSNotFound && count > 0 {
                for idx in 0..<count {
                    if let child = elem.accessibilityElement(at: idx),
                       let found = findAccessibilityElementFrame(containing: needle, in: child) {
                        return found
                    }
                }
            }
        }
        if let view = root as? UIView {
            for child in view.subviews {
                if let found = findAccessibilityElementFrame(containing: needle, in: child) {
                    return found
                }
            }
        }
        return nil
    }

    private func findScrollView(in root: UIView) -> UIScrollView? {
        if let scroll = root as? UIScrollView { return scroll }
        for child in root.subviews {
            if let found = findScrollView(in: child) { return found }
        }
        return nil
    }

    private func uiCategory(for dynamicTypeSize: DynamicTypeSize) -> UIContentSizeCategory {
        dynamicTypeSize == .accessibility5 ? .accessibilityExtraExtraExtraLarge : .large
    }

    private func recognizeText(in image: UIImage) throws -> String {
        guard let cg = image.cgImage else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: " | ")
    }

    private func savePNG(_ image: UIImage, to url: URL) throws {
        try XCTUnwrap(image.pngData()).write(to: url)
    }

    #endif
}
