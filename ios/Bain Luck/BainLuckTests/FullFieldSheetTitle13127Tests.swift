import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13127 (`1.0.7`): `FuturesAtlasFullFieldSheetView11666` wraps the full market headline
/// (`"Grammys 2027: Song of the Year"`) at the top of the sheet instead of clipping it in
/// `UINavigationBar`'s single-line inline slot (`"Grammys 2027: Song of th…"`).
@MainActor
final class FullFieldSheetTitle13127Tests: XCTestCase {

    private func grammysSongOfTheYearMarket() throws -> FuturesMarketDetail {
        let json = """
        {
          "id": 58492243,
          "name": "Grammys 2027: Song of the Year Winner",
          "category": "entertainment",
          "status": "open",
          "mutually_exclusive": true,
          "outcomes": [
            {"id": 1, "name": "Choosin' Texas — Ella Langley", "probability": 0.32, "opening_probability": 0.13},
            {"id": 2, "name": "the cure — Olivia Rodrigo", "probability": 0.22, "opening_probability": 0.16},
            {"id": 3, "name": "WHERE IS MY HUSBAND! — RAYE", "probability": 0.16, "opening_probability": 0.25},
            {"id": 4, "name": "Man I Need — Olivia Dean", "probability": 0.15, "opening_probability": 0.09},
            {"id": 5, "name": "Berghain — ROSALÍA", "probability": 0.07, "opening_probability": 0.06},
            {"id": 6, "name": "I Knew It, I Knew You — Taylor Swift", "probability": 0.05, "opening_probability": 0.05},
            {"id": 7, "name": "hate that i made you love me — Ariana Grande", "probability": 0.04, "opening_probability": 0.04},
            {"id": 8, "name": "Risk It All — Bruno Mars", "probability": 0.04, "opening_probability": 0.04}
          ]
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FuturesMarketDetail.self, from: Data(json.utf8))
    }

    private func captureSheetSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        sizeCategory: UIContentSizeCategory = .large,
        dynamicType: DynamicTypeSize = .large,
        width: CGFloat = 390,
        height: CGFloat = 760
    ) async throws -> UIImage {
        let host = hostForMeasurement(
            content
                .environment(\.colorScheme, scheme)
                .environment(\.dynamicTypeSize, dynamicType),
            at: dynamicType
        )
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
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 550_000_000)
        for _ in 0..<6 {
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

    private func recognizeLines(in image: UIImage) throws -> [String] {
        let upscaledSize = CGSize(width: image.size.width * 2, height: image.size.height * 2)
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

    func testGrammysVenueLossShowsOutAfterTheContenders() async throws {
        let payload = """
        {
          "id": 58492243,
          "name": "Grammys 2027: Song of the Year Winner",
          "category": "entertainment",
          "status": "open",
          "mutually_exclusive": true,
          "outcomes": [
            {"id": 217003204, "name": "I Just Might — Bruno Mars", "probability": 0.0,
             "is_winner": false, "resolution_source": "api_settlement", "is_out": true},
            {"id": 217003206, "name": "the cure — Olivia Rodrigo", "probability": 0.2405},
            {"id": 217003202, "name": "Man I Need — Olivia Dean", "probability": 0.1165}
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let market = try decoder.decode(FuturesMarketDetail.self, from: Data(payload.utf8))
        let presentation = FuturesAtlasPresentation11666.build(market: market)
        let row = try XCTUnwrap(presentation.body.allRows.last)
        XCTAssertEqual(row.id, 217003204)
        XCTAssertEqual(row.displayValue.primaryLabel, "Out")
        XCTAssertNil(row.displayValue.asOfText)
        XCTAssertNil(row.openingText)
        XCTAssertEqual(presentation.header.selectedOutcomeId, 217003206)

        let sheet = FuturesAtlasFullFieldSheetView11666(
            marketTitle: presentation.header.marketTitle,
            subtitleBadge: presentation.body.subtitleBadge,
            rows: presentation.body.allRows,
            selectedOutcomeId: presentation.header.selectedOutcomeId,
            showsRank: true,
            onSelectOutcome: { _ in }
        )
        let image = try await captureSheetSnapshot(sheet, scheme: .light)
        let text = try recognizeLines(in: image).joined(separator: " ")
        XCTAssertTrue(text.contains("Out"))
        XCTAssertFalse(text.contains("#3"))

        let attachment = XCTAttachment(image: image)
        attachment.name = "13127-grammys-out-390"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testFullFieldSheetWrapsGrammysSongOfTheYearTitleWithZeroEllipsis() async throws {
        let market = try grammysSongOfTheYearMarket()
        let presentation = FuturesAtlasPresentation11666.build(market: market)

        let makeSheet = {
            FuturesAtlasFullFieldSheetView11666(
                marketTitle: presentation.header.marketTitle,
                subtitleBadge: presentation.body.subtitleBadge,
                rows: presentation.body.allRows,
                selectedOutcomeId: presentation.header.selectedOutcomeId,
                showsRank: !presentation.body.shape.isNumericallyOrdered,
                onSelectOutcome: { _ in }
            )
        }

        let lightDefault = try await captureSheetSnapshot(makeSheet(), scheme: .light)
        let darkDefault = try await captureSheetSnapshot(makeSheet(), scheme: .dark)
        let lightLargest = try await captureSheetSnapshot(
            makeSheet(),
            scheme: .light,
            sizeCategory: .accessibilityExtraExtraLarge,
            dynamicType: .accessibility3,
            width: 390,
            height: 840
        )

        for (label, img) in [("default", lightDefault), ("largest", lightLargest)] {
            let joined = try recognizeLines(in: img).joined(separator: " | ")
            for word in ["Grammys", "2027", "Song", "Year"] {
                XCTAssertTrue(
                    joined.localizedCaseInsensitiveContains(word),
                    "[\(label)] Expected whole title word '\(word)' in full-field sheet; OCR: \(joined)"
                )
            }
            XCTAssertFalse(
                joined.contains("…") || joined.contains("..."),
                "[\(label)] Full-field sheet title and rows must never end in '…': \(joined)"
            )
        }

        if let outDir = ProcessInfo.processInfo.environment["RENDER_13127_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            try XCTUnwrap(lightDefault.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13127-grammys-sheet-title-light-390.png"))
            try XCTUnwrap(darkDefault.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13127-grammys-sheet-title-dark-390.png"))
            try XCTUnwrap(lightLargest.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13127-grammys-sheet-title-largest-390.png"))
        }
    }
}
