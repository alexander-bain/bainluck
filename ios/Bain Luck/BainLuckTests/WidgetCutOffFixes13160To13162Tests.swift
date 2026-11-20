import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// Pins the 1.0.7 widget cut-off fixes from the `5823` simulator sweep:
/// - #13160: Lock Screen rectangular saved-market widget (`157×66 pt`) never cuts off
///   market headline or outcome name with `"…"`.
/// - #13161: Home Screen small/medium saved-market widget (`155×155` / `329×155 pt`)
///   never cuts off market headline at `.xxxLarge` or outcome name at default text.
/// - #13162: Home Screen Medium (`329×155 pt`) & Large (`329×345 pt`) `BainLuckWidget`
///   never split 2/3-digit live scores vertically or cut off market headlines with `"…"`.
@MainActor
final class WidgetCutOffFixes13160To13162Tests: XCTestCase {

    #if canImport(UIKit)
    private func renderImage<V: View>(
        _ content: V,
        scheme: ColorScheme,
        sizeCategory: UIContentSizeCategory,
        typeSize: DynamicTypeSize,
        width: CGFloat,
        height: CGFloat
    ) throws -> UIImage {
        let wrapped = content
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, typeSize)
        let host = hostForMeasurement(wrapped, at: typeSize)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = sizeCategory

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = sizeCategory
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func ocrStrings(in image: UIImage) throws -> [String] {
        let upscaledSize = CGSize(width: image.size.width * 3, height: image.size.height * 3)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        let hiRes = UIGraphicsImageRenderer(size: upscaledSize, format: fmt).image { _ in
            image.draw(in: CGRect(origin: .zero, size: upscaledSize))
        }
        let cgImage = try XCTUnwrap(hiRes.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testLockScreenMarketRectangle13160DrawsWholeHeadlineAndOutcomeWithoutEllipsis() throws {
        let grammysRow = SavedWidgetReading10875.Row(
            label: "Choosin' Texas - Ella Langley",
            shortLabel: "Choosin' Texas - Ella Langley",
            figure: "35%",
            verdict: nil,
            emphasized: false
        )
        let spainRow = SavedWidgetReading10875.Row(
            label: "Alberto Núñez Feijóo",
            shortLabel: "Alberto Núñez Feijóo",
            figure: "63%",
            verdict: nil,
            emphasized: false
        )

        let stack = VStack(spacing: 14) {
            SavedMarketLockRectangleView13160(
                shortSubject: "Grammys 2027: Song of the Year",
                headline: grammysRow,
                footer: "As of 10:35 PM"
            )
            .padding(8)
            .frame(width: 173, height: 76)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color.secondary.opacity(0.14)))

            SavedMarketLockRectangleView13160(
                shortSubject: "Next Prime Minister of Spain after 2027 election?",
                headline: spainRow,
                footer: "As of 10:35 PM"
            )
            .padding(8)
            .frame(width: 173, height: 76)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color.secondary.opacity(0.14)))
        }
        .padding(.vertical, 16)
        .frame(width: 390)
        .background(Color(.systemBackground))

        for (cat, dt, label) in [(UIContentSizeCategory.large, DynamicTypeSize.large, "default"),
                                 (.extraExtraExtraLarge, .xxxLarge, "largest")] {
            for scheme in [ColorScheme.light, .dark] {
                let img = try renderImage(stack, scheme: scheme, sizeCategory: cat, typeSize: dt, width: 390, height: 210)
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " | ")
                XCTAssertFalse(joined.contains("…"), "Lock Screen rectangle (\(label), \(scheme)) truncated with '…': \(joined)")
                XCTAssertFalse(joined.contains("..."), "Lock Screen rectangle (\(label), \(scheme)) truncated with '...': \(joined)")
                for token in ["Grammys", "Year", "Langley", "35%", "Spain", "election", "63%"] {
                    XCTAssertTrue(
                        joined.localizedCaseInsensitiveContains(token),
                        "Missing '\(token)' in Lock Screen rectangle (\(label), \(scheme)): \(joined)"
                    )
                }
                if let dir = ProcessInfo.processInfo.environment["RENDER_13160_DIR"], !dir.isEmpty {
                    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                    let schemeTag = scheme == .light ? "light" : "dark"
                    try XCTUnwrap(img.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13160-lock-rect-\(label)-\(schemeTag)-390.png"))
                }
            }
        }
    }

    func testHomeSmallAndMediumSavedMarketWidget13161DrawsWholeSubjectAndOutcome() throws {
        let grammysRow = SavedWidgetReading10875.Row(
            label: "Choosin' Texas - Ella Langley",
            shortLabel: "Choosin' Texas - Ella Langley",
            figure: "35%",
            verdict: nil,
            emphasized: false
        )
        let spainRow = SavedWidgetReading10875.Row(
            label: "Alberto Núñez Feijóo",
            shortLabel: "Alberto Núñez Feijóo",
            figure: "63%",
            verdict: nil,
            emphasized: false
        )

        let showcase = VStack(spacing: 14) {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    SavedMarketWidgetHeaderAndOutcome13161(
                        subject: "Grammys 2027: Song of the Year",
                        isMediumFamily: false,
                        headline: grammysRow
                    )
                    Capsule().fill(Color.white.opacity(0.35)).frame(height: 7)
                    Text("As of 10:35 PM")
                        .font(.system(size: 10.5))
                        .opacity(0.8)
                        .lineLimit(1)
                }
                .foregroundStyle(.white)
                .padding(14)
                .frame(width: 155, height: 155)
                .background(RoundedRectangle(cornerRadius: 22).fill(Color(hex: "#059669")))

                VStack(alignment: .leading, spacing: 4) {
                    SavedMarketWidgetHeaderAndOutcome13161(
                        subject: "Next Prime Minister of Spain after 2027 election?",
                        isMediumFamily: false,
                        headline: spainRow
                    )
                    Capsule().fill(Color.white.opacity(0.35)).frame(height: 7)
                    Text("As of 10:35 PM")
                        .font(.system(size: 10.5))
                        .opacity(0.8)
                        .lineLimit(1)
                }
                .foregroundStyle(.white)
                .padding(14)
                .frame(width: 155, height: 155)
                .background(RoundedRectangle(cornerRadius: 22).fill(Color(hex: "#059669")))
            }

            VStack(alignment: .leading, spacing: 4) {
                SavedMarketWidgetHeaderAndOutcome13161(
                    subject: "Grammys 2027: Song of the Year",
                    isMediumFamily: true,
                    headline: grammysRow
                )
                Capsule().fill(Color.white.opacity(0.35)).frame(height: 7)
                Text("As of 10:35 PM")
                    .font(.system(size: 10.5))
                    .opacity(0.8)
                    .lineLimit(1)
            }
            .foregroundStyle(.white)
            .padding(14)
            .frame(width: 329, height: 155)
            .background(RoundedRectangle(cornerRadius: 22).fill(Color(hex: "#059669")))
        }
        .padding(.vertical, 16)
        .frame(width: 390)
        .background(Color(.systemBackground))

        for (cat, dt, label) in [(UIContentSizeCategory.large, DynamicTypeSize.large, "default"),
                                 (.extraExtraExtraLarge, .xxxLarge, "largest")] {
            for scheme in [ColorScheme.light, .dark] {
                let img = try renderImage(showcase, scheme: scheme, sizeCategory: cat, typeSize: dt, width: 390, height: 365)
                let joined = try ocrStrings(in: img).joined(separator: " | ")
                XCTAssertFalse(joined.contains("…"), "Saved market widget (\(label), \(scheme)) truncated with '…': \(joined)")
                XCTAssertFalse(joined.contains("..."), "Saved market widget (\(label), \(scheme)) truncated with '...': \(joined)")
                for token in ["Grammys", "Year", "Langley", "35%", "Spain", "election", "63%"] {
                    XCTAssertTrue(
                        joined.localizedCaseInsensitiveContains(token),
                        "Missing '\(token)' in Saved market widget (\(label), \(scheme)): \(joined)"
                    )
                }
                if let dir = ProcessInfo.processInfo.environment["RENDER_13160_DIR"], !dir.isEmpty {
                    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                    let schemeTag = scheme == .light ? "light" : "dark"
                    try XCTUnwrap(img.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13161-home-market-\(label)-\(schemeTag)-390.png"))
                }
            }
        }
    }

    func testMediumAndLargeLiveGamesWidgets13162KeepMultiDigitScoresOnOneLineAndMarketTitlesWhole() throws {
        let games: [WidgetDashboardGameRow13162] = [
            .init(id: 15351222, awayAbbrev: "HOU", homeAbbrev: "NOP", awayScore: 78, homeScore: 67, awayProb: 74, homeProb: 26, period: "Q3 5:12", sport: "NBA", awayColorHex: "#CE1141", homeColorHex: "#0C2340", awayDarkColorHex: nil, homeDarkColorHex: nil),
            .init(id: 15351223, awayAbbrev: "GSW", homeAbbrev: "LAL", awayScore: 114, homeScore: 109, awayProb: 81, homeProb: 19, period: "Q4 1:48", sport: "NBA", awayColorHex: "#1D428A", homeColorHex: "#552583", awayDarkColorHex: nil, homeDarkColorHex: nil),
            .init(id: 15351224, awayAbbrev: "DAL", homeAbbrev: "VGK", awayScore: 3, homeScore: 2, awayProb: 62, homeProb: 38, period: "3rd 8:10", sport: "NHL", awayColorHex: "#006847", homeColorHex: "#B4975A", awayDarkColorHex: nil, homeDarkColorHex: nil)
        ]
        let markets: [WidgetDashboardMarketRow13162] = [
            .init(id: 58492243, name: "Grammys 2027: Song of the Year", category: "Culture", leader: "Choosin' Texas", probability: 35, movement: 6),
            .init(id: 70732799, name: "Next Prime Minister of Spain after 2027?", category: "Politics", leader: "Alberto Núñez Feijóo", probability: 63, movement: 2),
            .init(id: 27467306, name: "TIME Person of the Year 2026", category: "Culture", leader: "Artificial Intelligence", probability: 29, movement: -1)
        ]

        let dashboardStack = VStack(spacing: 16) {
            MediumDashboardContentView13162(liveGames: games, discoverItems: markets)
                .frame(width: 329, height: 155)
                .background(RoundedRectangle(cornerRadius: 22).fill(Color(.secondarySystemBackground)))

            LargeDashboardContentView13162(liveGames: games, discoverItems: markets)
                .frame(width: 329, height: 345)
                .background(RoundedRectangle(cornerRadius: 22).fill(Color(.secondarySystemBackground)))
        }
        .padding(.vertical, 16)
        .frame(width: 390)
        .background(Color(.systemBackground))

        for (cat, dt, label) in [(UIContentSizeCategory.large, DynamicTypeSize.large, "default"),
                                 (.extraExtraExtraLarge, .xxxLarge, "largest")] {
            for scheme in [ColorScheme.light, .dark] {
                let img = try renderImage(dashboardStack, scheme: scheme, sizeCategory: cat, typeSize: dt, width: 390, height: 548)
                let joined = try ocrStrings(in: img).joined(separator: " | ")
                XCTAssertFalse(joined.contains("…"), "Dashboard widget (\(label), \(scheme)) truncated with '…': \(joined)")
                XCTAssertFalse(joined.contains("..."), "Dashboard widget (\(label), \(scheme)) truncated with '...': \(joined)")
                for token in ["78", "67", "114", "109", "Grammys", "Year", "Spain", "TIME", "2026"] {
                    XCTAssertTrue(
                        joined.localizedCaseInsensitiveContains(token),
                        "Missing intact token '\(token)' in Dashboard widget (\(label), \(scheme)): \(joined)"
                    )
                }
                if let dir = ProcessInfo.processInfo.environment["RENDER_13160_DIR"], !dir.isEmpty {
                    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                    let schemeTag = scheme == .light ? "light" : "dark"
                    try XCTUnwrap(img.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13162-dashboard-\(label)-\(schemeTag)-390.png"))
                }
            }
        }
    }
    #endif
}
