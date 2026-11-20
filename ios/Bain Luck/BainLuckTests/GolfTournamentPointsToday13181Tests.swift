import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13181 — Golf tournament card prints "+12.7 points today" in place of "+12.7pp today",
/// never "pp" or "pts", and fits on a single line at 390 pt default text size.
@MainActor
final class GolfTournamentPointsToday13181Tests: XCTestCase {

    func testMovementTodayTextUsesPointsNeverPpOrPts() {
        XCTAssertEqual(NativeTournamentDiscoverCard.movementTodayText(12.7), "+12.7 points today")
        XCTAssertEqual(NativeTournamentDiscoverCard.movementTodayText(-2.3), "-2.3 points today")
        XCTAssertEqual(NativeTournamentDiscoverCard.movementTodayText(1.0), "+1.0 points today")
        XCTAssertFalse(NativeTournamentDiscoverCard.movementTodayText(12.7).contains("pp"))
        XCTAssertFalse(NativeTournamentDiscoverCard.movementTodayText(12.7).contains("pts"))
    }

    #if canImport(UIKit)
    private func renderCard(
        _ data: FeedTournamentData,
        feedContext: String,
        dynamicTypeSize: DynamicTypeSize,
        colorScheme: ColorScheme
    ) throws -> UIImage {
        let uiCategory: UIContentSizeCategory
        switch dynamicTypeSize {
        case .accessibility5: uiCategory = .accessibilityExtraExtraExtraLarge
        case .xxxLarge: uiCategory = .extraExtraExtraLarge
        default: uiCategory = .large
        }
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light

        let wrapped = VStack(spacing: 0) {
            NativeTournamentDiscoverCard(
                data: data,
                feedContext: feedContext,
                navigationPath: .constant(NavigationPath())
            )
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 16)
        .frame(width: 390, alignment: .top)
        .fixedSize(horizontal: false, vertical: true)
        .background(Color(.systemGroupedBackground))
        .environment(\.dynamicTypeSize, dynamicTypeSize)
        .environment(\.colorScheme, colorScheme)
        .environmentObject(PinManager())

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = uiCategory

        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }

        let initialBounds = CGRect(x: 0, y: 0, width: 390, height: 1400)
        let window = UIWindow(windowScene: scene)
        window.frame = initialBounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = uiCategory
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = initialBounds
        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        let fitted = host.sizeThatFits(in: CGSize(width: 390, height: 2400))
        let height = ceil(max(fitted.height, 220))
        let bounds = CGRect(x: 0, y: 0, width: 390, height: height)
        window.frame = bounds
        host.view.frame = bounds
        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func ocrObservations(in image: UIImage) throws -> [VNRecognizedTextObservation] {
        let up = CGSize(width: image.size.width * 3, height: image.size.height * 3)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        let hiRes = UIGraphicsImageRenderer(size: up, format: fmt).image { _ in
            image.draw(in: CGRect(origin: .zero, size: up))
        }
        let cg = try XCTUnwrap(hiRes.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return req.results ?? []
    }

    func testGolfCardPrintsPlus12Point7PointsTodayOnOneLineAt390DefaultText() throws {
        let json = #"""
        {
          "key": "lpga_cme_group_tour_championship",
          "name": "CME Group Tour Championship",
          "slug": "cme-group-tour-championship",
          "tour": "lpga",
          "tour_label": "LPGA Tour",
          "is_major": false,
          "venue": "Tiburon Golf Club",
          "location": "Naples, FL",
          "schedule_status": "in_progress",
          "golfers": [
            {"name": "Jeeno Thitikul", "probability": 0.43, "rendered_percent": 43, "rank": 1, "movement_24h": 0.127},
            {"name": "Nelly Korda", "probability": 0.22, "rendered_percent": 22, "rank": 2, "movement_24h": -0.031},
            {"name": "Lydia Ko", "probability": 0.11, "rendered_percent": 11, "rank": 3, "movement_24h": 0.015},
            {"name": "Ruoning Yin", "probability": 0.08, "rendered_percent": 8, "rank": 4, "movement_24h": -0.012}
          ],
          "source_count": 3,
          "is_marquee": false,
          "marquee_whathit": false
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(FeedTournamentData.self, from: Data(json.utf8))

        var defaultPair: [ColorScheme: UIImage] = [:]
        for scheme in [ColorScheme.light, .dark] {
            let img = try renderCard(
                data,
                feedContext: "Round 3 underway in Naples.",
                dynamicTypeSize: .large,
                colorScheme: scheme
            )
            defaultPair[scheme] = img
            let obs = try ocrObservations(in: img)
            let strings = obs.compactMap { $0.topCandidates(1).first?.string }
            let joined = strings.joined(separator: " | ")
            XCTAssertFalse(joined.contains("…") || joined.contains("..."), "Truncated at 390 default (\(scheme)): \(joined)")
            XCTAssertFalse(joined.contains("12.7pp"), "Still printed pp (\(scheme)): \(joined)")
            // Confirm '+12.7 points today' sits on one single Vision line observation at 390 pt default text
            let singleLineMatch = strings.first { line in
                line.localizedCaseInsensitiveContains("12.7 points today")
            }
            XCTAssertNotNil(singleLineMatch, "Expected '+12.7 points today' on one line at 390 default (\(scheme)), got: \(joined)")
        }

        if let dir = ProcessInfo.processInfo.environment["EXPORT_13181_RENDERS_DIR"], !dir.isEmpty {
            try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            let light = try XCTUnwrap(defaultPair[.light])
            let dark = try XCTUnwrap(defaultPair[.dark])
            let gap: CGFloat = 16
            let w = light.size.width + gap + dark.size.width
            let h = max(light.size.height, dark.size.height)
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let sheet = UIGraphicsImageRenderer(size: CGSize(width: w, height: h), format: fmt).image { ctx in
                UIColor(white: 0.12, alpha: 1).setFill()
                ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
                light.draw(at: .zero)
                dark.draw(at: CGPoint(x: light.size.width + gap, y: 0))
            }
            try XCTUnwrap(sheet.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13181-golf-points-today-390.png"))
        }
    }
    #endif
}
