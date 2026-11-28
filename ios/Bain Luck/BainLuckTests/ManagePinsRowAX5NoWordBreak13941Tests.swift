import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// #13941 (`PILLAR: FORMATTING`):
/// Verifies at `.accessibility5` across `320 pt` and `390 pt` (Light & Dark) that the
/// `"Manage pins"` row in `MyStuffView` never breaks `"Manage"` mid-word (`"M / anage / pins"`,
/// `"Man- / age pins"`), keeps the saved-pin count and disclosure chevron on the row,
/// and leaves `.large` default text size identical to `master`.
@MainActor
final class ManagePinsRowAX5NoWordBreak13941Tests: XCTestCase {

    #if os(iOS)

    private nonisolated final class EmptyMyStuffFeedStub: MyStuffFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        init(feed: FeedResponse) { self.feed = feed }
        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                TeamFuturesResponse.self,
                from: Data(#"{"items":[],"team_ids":[],"total_count":0}"#.utf8)
            )
        }
    }

    private func decodeJSON<T: Decodable>(_ type: T.Type, json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(type, from: Data(json.utf8))
    }

    private func render<V: View>(
        _ view: V,
        into window: UIWindow,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let category: UIContentSizeCategory = dynamicTypeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large

        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.horizontalSizeClass, .compact)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = .compact
        host.traitOverrides.preferredContentSizeCategory = category
        host.view.traitOverrides.preferredContentSizeCategory = category

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private func ocrTexts(in image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func maybeSave(_ image: UIImage, name: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["MANAGE_PINS_13941_CAPTURE_DIR"], !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    private func assertManagePinsWholeWords(
        ocr: [String],
        panel: String,
        allowBeforeFail: Bool,
        expectedCount: String,
        requireSingleLineTitle: Bool = false
    ) {
        let joined = ocr.joined(separator: " | ")
        print("MANAGE_PINS_13941_OCR \(panel) lines=\(ocr.count) text=\(joined)")
        guard !allowBeforeFail else { return }

        let brokenMarkers = ["Man-", "\u{2026}", "..."]
        for marker in brokenMarkers {
            XCTAssertFalse(
                ocr.contains { $0.localizedCaseInsensitiveContains(marker) },
                "\(panel): Manage pins broke mid-word (`\(marker)`) in OCR: \(joined)"
            )
        }
        let combined = ocr.joined(separator: " ")
        XCTAssertNil(
            combined.range(of: #"\banage\b"#, options: [.regularExpression, .caseInsensitive]),
            "\(panel): Manage pins broke into standalone fragment 'anage' in OCR: \(joined)"
        )
        XCTAssertTrue(
            combined.range(of: #"\bManage\b"#, options: [.regularExpression, .caseInsensitive]) != nil,
            "\(panel): expected intact whole word 'Manage' in OCR: \(joined)"
        )
        XCTAssertTrue(
            combined.range(of: #"\bpins\b"#, options: [.regularExpression, .caseInsensitive]) != nil,
            "\(panel): expected intact whole word 'pins' in OCR: \(joined)"
        )
        if requireSingleLineTitle {
            XCTAssertTrue(
                ocr.contains { $0.localizedCaseInsensitiveContains("Manage pins") },
                "\(panel): default size must keep 'Manage pins' on a single line in OCR: \(joined)"
            )
        }
        if !expectedCount.isEmpty {
            XCTAssertTrue(
                combined.range(of: #"\b"# + NSRegularExpression.escapedPattern(for: expectedCount) + #"\b"#, options: .regularExpression) != nil,
                "\(panel): expected saved-pin count '\(expectedCount)' in OCR: \(joined)"
            )
        }
    }

    func testSharedAccessibilityFontSizeContracts() {
        let constrained = ManagePinsHeaderRowLabel13941.sharedAccessibilityFontSize(
            baseSize: 45,
            availableWidth: 120
        )
        XCTAssertLessThan(constrained, 45)
        XCTAssertGreaterThanOrEqual(constrained, 45 * 0.45)

        let wide = ManagePinsHeaderRowLabel13941.sharedAccessibilityFontSize(
            baseSize: 45,
            availableWidth: 320
        )
        XCTAssertEqual(wide, 45, accuracy: 0.01)

        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/ManagePinsHeaderRowLabel13941.swift")
        let source = try! String(contentsOf: sourceURL, encoding: .utf8)
        let ordinarySplit = source.components(separatedBy: "private var accessibilityRow: some View")
        XCTAssertEqual(ordinarySplit.count, 2)
        let ordinarySection = ordinarySplit[0]
        let accessibilitySection = ordinarySplit[1]
        XCTAssertTrue(ordinarySection.contains("Text(\"\\(savedPinCount)\")"))
        XCTAssertTrue(ordinarySection.contains("\"chevron.right\""))
        XCTAssertTrue(accessibilitySection.contains("Text(\"\\(savedPinCount)\")"))
        XCTAssertTrue(accessibilitySection.contains("\"chevron.right\""))
    }

    func testManagePinsRowNoMidWordBreakAt320And390AX5AndDefaultSizeIntact() async throws {
        let allowBeforeFail = ProcessInfo.processInfo.environment["MANAGE_PINS_13941_ALLOW_BEFORE_FAIL"] == "1"
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let upcomingTime = iso.string(from: Date().addingTimeInterval(3 * 3600))

        let upcomingJSON = """
        {
          "id": 9239410,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Baltimore Ravens",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"team_id": 33, "name": "Baltimore Ravens", "short_name": "Ravens", "abbreviation": "BAL", "primary_color": "#241773"},
          "home_team_data": {"team_id": 4, "name": "Cincinnati Bengals", "short_name": "Bengals", "abbreviation": "CIN", "primary_color": "#FB4F14"},
          "commence_time": "\(upcomingTime)",
          "status": "scheduled",
          "current_odds": {"away_probability": 0.61, "home_probability": 0.39, "away_rendered_percent": 61, "home_rendered_percent": 39}
        }
        """

        let myStuffFeed = try decodeJSON(FeedResponse.self, json: """
        {
          "items": [
            {"type": "event", "score": 95, "data": \(upcomingJSON)}
          ],
          "total": 1,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """)

        let suiteName = "manage-pins-13941-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }

        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = AuthUser(
            id: 42,
            email: "reader@example.com",
            displayName: "Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        let followManager = FollowManager295A(defaults: defaults)
        let alertsPrompt = GameAlertsPromptController295A(defaults: defaults, requestPermissionHandler: {})
        let checklistStore = FirstRunChecklistStore364A(defaults: defaults)
        checklistStore.dismissFromMyStuff()

        let myStuffVM = MyStuffViewModel(
            client: EmptyMyStuffFeedStub(feed: myStuffFeed),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await myStuffVM.startLoad()

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 800))
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let ax5Configs: [(width: CGFloat, scheme: ColorScheme, tag: String)] = [
            (320, .light, "320_ax5_light"),
            (320, .dark, "320_ax5_dark"),
            (390, .light, "390_ax5_light"),
            (390, .dark, "390_ax5_dark"),
        ]

        for cfg in ax5Configs {
            let img = render(
                MyStuffView(viewModelForTest: myStuffVM)
                    .environmentObject(authManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(pinManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.firstRunChecklistStore364A, checklistStore)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: cfg.width,
                height: 760,
                colorScheme: cfg.scheme,
                dynamicTypeSize: .accessibility5
            )
            try maybeSave(img, name: "mystuff_\(cfg.tag)")
            assertManagePinsWholeWords(
                ocr: try ocrTexts(in: img),
                panel: "mystuff_\(cfg.tag)",
                allowBeforeFail: allowBeforeFail,
                expectedCount: ""
            )
        }

        // Default text size parity beside master
        for (scheme, tag) in [(ColorScheme.light, "390_default_light"), (ColorScheme.dark, "390_default_dark")] {
            let img = render(
                MyStuffView(viewModelForTest: myStuffVM)
                    .environmentObject(authManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(pinManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.firstRunChecklistStore364A, checklistStore)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: 390,
                height: 520,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )
            try maybeSave(img, name: "mystuff_\(tag)")
            assertManagePinsWholeWords(
                ocr: try ocrTexts(in: img),
                panel: "mystuff_\(tag)",
                allowBeforeFail: allowBeforeFail,
                expectedCount: "",
                requireSingleLineTitle: true
            )
        }

        // Two-digit saved count guard on standalone card wrapper (Light & Dark across 320 & 390)
        for width in [CGFloat(320), CGFloat(390)] {
            for (scheme, schemeName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let card = ManagePinsHeaderRowLabel13941(savedPinCount: 12)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.cardBackgroundDark)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .padding(.horizontal, 16)
                let img = render(
                    card,
                    into: window,
                    width: width,
                    height: 220,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility5
                )
                let tag = "card_\(Int(width))_ax5_count12_\(schemeName)"
                try maybeSave(img, name: tag)
                assertManagePinsWholeWords(
                    ocr: try ocrTexts(in: img),
                    panel: tag,
                    allowBeforeFail: allowBeforeFail,
                    expectedCount: "12"
                )
            }
        }
    }

    #endif
}
