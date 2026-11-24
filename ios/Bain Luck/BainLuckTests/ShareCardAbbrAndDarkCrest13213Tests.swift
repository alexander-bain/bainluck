import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class ShareCardAbbrAndDarkCrest13213Tests: XCTestCase {

    // MARK: - Helpers

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func makeSolidCrestImage(color: UIColor, size: CGFloat = 64) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        return UIGraphicsImageRenderer(size: CGSize(width: size, height: size), format: format).image { ctx in
            color.setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: 12, y: 12, width: size - 24, height: size - 24))
        }
    }

    private func loadCrestImage(filename: String, fallbackColor: UIColor) -> UIImage {
        if let dir = ProcessInfo.processInfo.environment["BUILDER_C_CREST_DIR_13213"], !dir.isEmpty {
            let path = URL(fileURLWithPath: dir).appendingPathComponent(filename).path
            if let img = UIImage(contentsOfFile: path) {
                return img
            }
        }
        return makeSolidCrestImage(color: fallbackColor)
    }

    private func renderHostedInWindow<V: View>(
        _ view: V,
        scheme: ColorScheme,
        dynamicType: DynamicTypeSize,
        width: CGFloat = 390,
        height: CGFloat = 420
    ) async throws -> UIImage {
        let sizeCategory: UIContentSizeCategory = dynamicType.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large
        let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, scheme)
            .background(Color(.systemGroupedBackground))
        let host = hostForMeasurement(wrapped, at: dynamicType)
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = sizeCategory
        host.view.backgroundColor = scheme == .dark ? .black : .systemGroupedBackground

        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
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
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        // Allow TeamLogoView `.task` image cache lookup to settle before rasterizing.
        try? await Task.sleep(nanoseconds: 150_000_000)
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fitted = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
        let finalHeight = max(140, ceil(fitted.height))
        let finalBounds = CGRect(x: 0, y: 0, width: width, height: finalHeight)
        window.frame = finalBounds
        host.view.frame = finalBounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))

        let format = UIGraphicsImageRendererFormat()
        format.scale = 2
        format.opaque = true
        return UIGraphicsImageRenderer(bounds: finalBounds, format: format).image { ctx in
            if !window.drawHierarchy(in: finalBounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func ocrLines(in image: UIImage) throws -> [String] {
        let cgImage = try XCTUnwrap(image.cgImage)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func hasBrightContrastPixels(_ image: UIImage, inNormalizedRect rect: CGRect) -> Bool {
        guard let cg = image.cgImage else { return false }
        let pxRect = CGRect(
            x: rect.minX * CGFloat(cg.width),
            y: rect.minY * CGFloat(cg.height),
            width: rect.width * CGFloat(cg.width),
            height: rect.height * CGFloat(cg.height)
        ).integral
        guard let cropped = cg.cropping(to: pxRect) else { return false }
        let w = cropped.width
        let h = cropped.height
        guard w > 0, h > 0 else { return false }
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(
            data: &bytes,
            width: w,
            height: h,
            bitsPerComponent: 8,
            bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
        ) else {
            return false
        }
        ctx.draw(cropped, in: CGRect(x: 0, y: 0, width: w, height: h))
        var brightPixels = 0
        for idx in stride(from: 0, to: bytes.count, by: 4) {
            let r = Double(bytes[idx]) / 255.0
            let g = Double(bytes[idx + 1]) / 255.0
            let b = Double(bytes[idx + 2]) / 255.0
            let lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if lum > 0.78 {
                brightPixels += 1
            }
        }
        return brightPixels > 20
    }

    // MARK: - 1. Share Card Served Team Abbreviations (#13213)

    func testShareCardCrestLabelsUseServedAbbreviationsAndFallBackWhenMissing() throws {
        let served = ShareableEventCardView.crestLabels(
            awayTeam: "Philadelphia Flyers",
            homeTeam: "Ottawa Senators",
            awayAbbreviation: "PHI",
            homeAbbreviation: "OTT",
            sportKey: "icehockey_nhl"
        )
        XCTAssertEqual(served.away, "PHI")
        XCTAssertEqual(served.home, "OTT")

        let fallback = ShareableEventCardView.crestLabels(
            awayTeam: "Philadelphia Flyers",
            homeTeam: "Ottawa Senators",
            awayAbbreviation: nil,
            homeAbbreviation: "   ",
            sportKey: "icehockey_nhl"
        )
        XCTAssertEqual(fallback.away, "FLY")
        XCTAssertEqual(fallback.home, "SEN")

        // Source-level guard: DiscoverEventCard passes both served abbreviations on BOTH share-card paths.
        let discoverCardPath = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/DiscoverEventCard.swift")
        let source = try String(contentsOf: discoverCardPath, encoding: .utf8)
        let shareBody = source.components(separatedBy: "private func renderedShareImage()").dropFirst().first ?? ""
        let calls = shareBody.components(separatedBy: "ShareCardRenderer.renderEventCard(").dropFirst()
        XCTAssertEqual(calls.count, 2, "Expected both finished and active share card call sites")
        for call in calls {
            XCTAssertTrue(call.contains("awayAbbreviation: event.awayTeamData?.abbreviation"))
            XCTAssertTrue(call.contains("homeAbbreviation: event.homeTeamData?.abbreviation"))
            XCTAssertTrue(call.contains("sportKey: event.sport"))
        }
    }

    func testFinishedFlyersSenatorsShareCardRendersPHIAndOTTNotFLYAndSEN() throws {
        let pregame = PrematchReading(
            awayProbability: 0.41,
            homeProbability: 0.59,
            percents: [41, 59],
            source: "kalshi",
            isServed: true,
            awayIsComplement: false
        )

        let shareImage = try XCTUnwrap(ShareCardRenderer.renderEventCard(
            homeTeam: "Ottawa Senators",
            awayTeam: "Philadelphia Flyers",
            awayAbbreviation: "PHI",
            homeAbbreviation: "OTT",
            homeProbability: pregame.homeProbability,
            awayProbability: pregame.awayProbability,
            awayRenderedPercent: pregame.percents.first ?? nil,
            homeRenderedPercent: pregame.percents.count > 1 ? pregame.percents[1] : nil,
            sportName: "NHL",
            homeColor: Color(hex: "#C52032"),
            awayColor: Color(hex: "#F74902"),
            status: "completed",
            homeScore: 5,
            awayScore: 6,
            commenceTime: Date().addingTimeInterval(-10800),
            pregameReading: pregame,
            sportKey: "icehockey_nhl",
            authorityPeriod: nil
        ))

        let joined = try ocrLines(in: shareImage).joined(separator: " | ")
        XCTAssertFalse(joined.contains("…"), "Share card truncated with ellipsis: \(joined)")
        XCTAssertFalse(joined.contains("FLY"), "Share card still printed nickname code FLY: \(joined)")
        XCTAssertFalse(joined.contains("SEN"), "Share card still printed nickname code SEN: \(joined)")
        for expected in ["PHI", "OTT", "Philadelphia Flyers", "Ottawa Senators", "FINAL", "6", "5", "41%", "59%"] {
            XCTAssertTrue(
                joined.localizedCaseInsensitiveContains(expected),
                "Share card missing '\(expected)' in OCR: \(joined)"
            )
        }

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13213"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            let framed = UIGraphicsImageRenderer(size: CGSize(width: 390, height: 520)).image { ctx in
                UIColor.systemBackground.setFill()
                ctx.fill(CGRect(x: 0, y: 0, width: 390, height: 520))
                shareImage.draw(in: CGRect(x: 7.5, y: 10, width: 375, height: 500))
            }
            try XCTUnwrap(framed.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/13213-share-card-phi-ott-390.png")
            )
        }
    }

    // MARK: - 2. Dark-Mode Dark Crest Contrast (Utah Jazz on Dark Discover Card)

    func testNeedsDarkSurfaceBackingDistinguishesDarkJazzCrestFromBrightCrests() {
        let darkNavyCrest = makeSolidCrestImage(color: UIColor(red: 12/255, green: 35/255, blue: 64/255, alpha: 1))
        let brightOrangeCrest = makeSolidCrestImage(color: UIColor(red: 247/255, green: 73/255, blue: 2/255, alpha: 1))
        XCTAssertTrue(TeamLogoView.needsDarkSurfaceBacking(darkNavyCrest))
        XCTAssertFalse(TeamLogoView.needsDarkSurfaceBacking(brightOrangeCrest))

        if let dir = ProcessInfo.processInfo.environment["BUILDER_C_CREST_DIR_13213"], !dir.isEmpty {
            if let utah = UIImage(contentsOfFile: "\(dir)/utah.png") {
                XCTAssertTrue(TeamLogoView.needsDarkSurfaceBacking(utah), "Real Utah Jazz crest must get dark-mode backing")
            }
            if let phi = UIImage(contentsOfFile: "\(dir)/phi.png") {
                XCTAssertFalse(TeamLogoView.needsDarkSurfaceBacking(phi), "Flyers crest should not need backing")
            }
            if let ott = UIImage(contentsOfFile: "\(dir)/ott.png") {
                XCTAssertFalse(TeamLogoView.needsDarkSurfaceBacking(ott), "Senators crest should not need backing")
            }
        }
    }

    func testUtahJazzCrestHasContrastBackingOnDarkDiscoverCardAtDefaultAndAX5() async throws {
        let utahURLString = "https://a.espncdn.com/i/teamlogos/nba/500/utah.png"
        let bosURLString = "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"
        let utahURL = try XCTUnwrap(URL(string: utahURLString))
        let bosURL = try XCTUnwrap(URL(string: bosURLString))

        let utahImg = loadCrestImage(
            filename: "utah.png",
            fallbackColor: UIColor(red: 12/255, green: 35/255, blue: 64/255, alpha: 1)
        )
        let bosImg = loadCrestImage(
            filename: "bos.png",
            fallbackColor: UIColor(red: 0/255, green: 122/255, blue: 51/255, alpha: 1)
        )
        await ImageCache.shared.seedForTesting(utahImg, url: utahURL)
        await ImageCache.shared.seedForTesting(bosImg, url: bosURL)

        let jazzVsCeltics = try decodeEvent("""
        {
          "id": 15413213,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Boston Celtics",
          "commence_time": "2026-11-22T02:00:00Z",
          "status": "scheduled",
          "away_team_data": {
            "team_id": 26,
            "slug": "utah-jazz",
            "abbreviation": "UTA",
            "primary_color": "#0C2340",
            "logo_small": "\(utahURLString)"
          },
          "home_team_data": {
            "team_id": 2,
            "slug": "boston-celtics",
            "abbreviation": "BOS",
            "primary_color": "#007A33",
            "logo_small": "\(bosURLString)"
          },
          "current_odds": {
            "away_probability": 0.24,
            "home_probability": 0.76,
            "away_rendered_percent": 24,
            "home_rendered_percent": 76
          }
        }
        """)

        let darkColors = TeamTextContrast.darkSurfaceColorHexes(
            awayHex: "#0C2340",
            homeHex: "#007A33"
        )
        let card = DiscoverCompactSingleGameCard190CView(
            event: jazzVsCeltics,
            prematch: nil,
            awayColor: Color(hex: darkColors.away),
            homeColor: Color(hex: darkColors.home),
            projectionAndSuspendedLines: { EmptyView() },
            footerRow: { EmptyView() }
        )
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .padding(16)

        for (dynType, label) in [(DynamicTypeSize.large, "default"), (DynamicTypeSize.accessibility5, "ax5")] {
            let rendered = try await renderHostedInWindow(card, scheme: .dark, dynamicType: dynType, width: 390)
            let ocr = try ocrLines(in: rendered).joined(separator: " | ")
            XCTAssertFalse(ocr.contains("…"), "Dark Jazz card (\(label)) truncated with ellipsis: \(ocr)")
            XCTAssertTrue(ocr.localizedCaseInsensitiveContains("Jazz"), "Missing Jazz in Dark card (\(label)): \(ocr)")
            XCTAssertTrue(ocr.localizedCaseInsensitiveContains("Celtics"), "Missing Celtics in Dark card (\(label)): \(ocr)")
            XCTAssertTrue(
                hasBrightContrastPixels(rendered, inNormalizedRect: CGRect(x: 0.04, y: 0.15, width: 0.28, height: 0.55)),
                "Dark Jazz crest badge disc lacked visible light contrast pixels in Dark Mode (\(label))"
            )

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13213"], !outDir.isEmpty {
                try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
                try XCTUnwrap(rendered.pngData()).write(
                    to: URL(fileURLWithPath: "\(outDir)/13213-discover-jazz-dark-\(label)-390.png")
                )
            }
        }
    }
}
