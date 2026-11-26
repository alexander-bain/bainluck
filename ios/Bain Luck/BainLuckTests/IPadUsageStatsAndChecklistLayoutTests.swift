import Combine
import Foundation
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class IPadUsageStatsAndChecklistLayoutTests: XCTestCase {

    private func sampleChecklistContent() -> FirstRunChecklistContent364A {
        FirstRunChecklistContent364A(
            lookupExamples: [],
            startWithTonight: [],
            discoverSets: [],
            rowPreviews: [
                .lookUp: FirstRunChecklistRowPreview364A(
                    subtitle: "Search any game, team, award, or election",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "magnifyingglass",
                    accentHex: "#005CC2"
                ),
                .follow: FirstRunChecklistRowPreview364A(
                    subtitle: "Teams, cities, schools, or topics",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "star.fill",
                    accentHex: "#047857"
                ),
                .exploreSets: FirstRunChecklistRowPreview364A(
                    subtitle: "Pick topics to shape your Discover feed",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "square.grid.2x2.fill",
                    accentHex: "#7C3AED"
                ),
                .syncDevices: FirstRunChecklistRowPreview364A(
                    subtitle: "Sign in to sync across devices",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "laptopcomputer.and.iphone",
                    accentHex: "#005CC2"
                ),
                .alerts: FirstRunChecklistRowPreview364A(
                    subtitle: "Game starts & 15+ point swings",
                    percentText: nil,
                    imageUrl: nil,
                    sfSymbol: "bell.badge.fill",
                    accentHex: "#D97706"
                ),
            ],
            subjectArtByCategory: [:]
        )
    }

    func testIPadWidthsDoNotStretchOrClipUsageStatsAndChecklist() throws {
        let content = sampleChecklistContent()
        let suite = "IPadUsageStatsAndChecklistLayoutTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let followVM = FirstRunViewModel212A(initialPairs: [], defaults: defaults)
        let followManager = FollowManager295A(defaults: defaults)
        let widths: [CGFloat] = [390, 834, 1194]

        for width in widths {
            let promptHost = hostForMeasurement(
                TelemetryConsentPrompt { _ in }
                    .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
                    .frame(width: width),
                at: .large
            )
            let promptFit = promptHost.sizeThatFits(in: CGSize(width: width, height: 1400))
            XCTAssertLessThanOrEqual(promptFit.width, width + 1.0)

            let views: [AnyView] = [
                AnyView(
                    FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone)
                    )
                ),
                AnyView(
                    FirstRunLookupStepView364A(
                        examples: [],
                        query: .constant(""),
                        results: []
                    )
                ),
                AnyView(
                    FirstRunFollowStepView364A(
                        vm: followVM,
                        subjectArtByCategory: [:]
                    )
                    .environment(\.followManager295A, followManager)
                ),
                AnyView(
                    FirstRunExploreSetsStepView364A(
                        sets: [],
                        selectedSlugs: .constant([])
                    )
                ),
                AnyView(FirstRunSignInStepView364A()),
                AnyView(FirstRunAlertsStepView364A()),
            ]

            for subview in views {
                let host = hostForMeasurement(
                    NavigationStack { subview }
                        .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
                        .frame(width: width),
                    at: .large
                )
                let fit = host.sizeThatFits(in: CGSize(width: width, height: 1400))
                XCTAssertLessThanOrEqual(fit.width, width + 1.0)
            }
        }
    }

    func testPromptAndChecklistColumnsCapAtReadableWidth() throws {
        let testFile = URL(fileURLWithPath: #filePath)
        let repoRoot = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        let promptSrc = try String(
            contentsOf: repoRoot.appendingPathComponent("ios/Bain Luck/Bain Luck/Components/TelemetryConsentPrompt.swift"),
            encoding: .utf8
        )
        let checklistSrc = try String(
            contentsOf: repoRoot.appendingPathComponent("ios/Bain Luck/Bain Luck/Views/FirstRunChecklistView364A.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(promptSrc.contains("DS.cardBg"))
        XCTAssertTrue(promptSrc.contains("DS.surface"))
        XCTAssertTrue(promptSrc.contains("frame(maxWidth: 460)"))
        XCTAssertTrue(checklistSrc.contains("ChecklistColumn364A"))
        XCTAssertTrue(checklistSrc.contains("checklistReadableColumn364A"))
    }

    #if canImport(UIKit)
    func testRenderIPad834And1194LightDarkScreens() async throws {
        let outPath = ProcessInfo.processInfo.environment["IPAD_13261_SHOTS_DIR"] ?? ""
        let outDir = outPath.isEmpty
            ? FileManager.default.temporaryDirectory.appendingPathComponent("shots-ipad-item4", isDirectory: true)
            : URL(fileURLWithPath: outPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let content = sampleChecklistContent()
        let partialState = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: false
        )

        let specs: [(name: String, width: CGFloat, height: CGFloat, scheme: ColorScheme)] = [
            ("834-light", 834, 1194, .light),
            ("834-dark", 834, 1194, .dark),
            ("1194-light", 1194, 834, .light),
            ("1194-dark", 1194, 834, .dark),
        ]

        for spec in specs {
            try await renderView(
                TelemetryConsentPrompt { _ in },
                name: "usage-stats-\(spec.name)",
                width: spec.width,
                height: spec.height,
                colorScheme: spec.scheme,
                outDir: outDir
            )
            try await renderView(
                NavigationStack {
                    FirstRunChecklistView364A(
                        content: content,
                        state: .constant(partialState)
                    )
                },
                name: "checklist-\(spec.name)",
                width: spec.width,
                height: spec.height,
                colorScheme: spec.scheme,
                outDir: outDir
            )
            try await renderView(
                NavigationStack {
                    FirstRunChecklistView364A(
                        content: content,
                        state: .constant(.allDone)
                    )
                },
                name: "checklist-alldone-\(spec.name)",
                width: spec.width,
                height: spec.height,
                colorScheme: spec.scheme,
                outDir: outDir
            )
            try await renderView(
                NavigationStack {
                    FirstRunAlertsStepView364A()
                },
                name: "step-alerts-\(spec.name)",
                width: spec.width,
                height: spec.height,
                colorScheme: spec.scheme,
                outDir: outDir
            )
        }
    }

    private func renderView<V: View>(
        _ view: V,
        name: String,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        outDir: URL
    ) async throws {
        let auth = AuthManager(restoreOnInit: false)
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environmentObject(auth)
            .environment(\.colorScheme, colorScheme)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .environment(\.dynamicTypeSize, .large)
            .frame(width: width, height: height)

        let host = hostForMeasurement(wrapped, at: .large)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        host.view.traitOverrides.preferredContentSizeCategory = .large
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.overrideUserInterfaceStyle = uiStyle
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 30_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let pngURL = outDir.appendingPathComponent("\(name).png")
        try XCTUnwrap(image.pngData()).write(to: pngURL)
        print("SHOT_IPAD_ITEM4_PNG:", pngURL.path)
    }
    #endif
}
