import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13304 / Fable 7:06 AM PT assignment (1.0.7): `MachineryDiscoverCardView` draws `card.image_url`
/// when present inside a `2:1` frame that fills and centre-crops the picture (`.scaledToFill().clipped()`),
/// and leaves cards without `image_url` completely unchanged.
@MainActor
final class MachineryCardHeroImage13304Tests: XCTestCase {

    func testMachineryCardContractDecodesAndValidatesImageURL() throws {
        let withImage = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-white-christmas",
          "form_id": "benchmark_strip",
          "kicker": "WEATHER · CHRISTMAS",
          "title": "Pittsburgh is the likeliest white Christmas at 49%, with Minneapolis at 42%",
          "subtitle": "Chance of measurable snow on Christmas Day across U.S. cities.",
          "section_count": 1,
          "item_count": 11,
          "item_noun": "cities",
          "image_url": "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png",
          "image_alt": "U.S. map showing 11 cities shaded by chance of a white Christmas",
          "rows": [
            {"outcome_id": 1, "name": "Pittsburgh", "probability": 0.485, "rendered_percent": 49}
          ]
        }
        """#.utf8))
        XCTAssertEqual(
            withImage.imageUrl,
            "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png"
        )
        XCTAssertEqual(
            withImage.verifiedImageURL?.absoluteString,
            "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png"
        )
        XCTAssertEqual(
            withImage.imageAlt,
            "U.S. map showing 11 cities shaded by chance of a white Christmas"
        )

        let camelCase = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-who-gets-engaged",
          "formId": "benchmark_strip",
          "kicker": "ENTERTAINMENT · COUPLES",
          "title": "Couples to Watch",
          "imageUrl": "  https://api.bainluck.com/api/containers/machinery-who-gets-engaged/card-art.jpg  ",
          "imageAlt": "Stacked engagement ring and wedding bands",
          "rows": []
        }
        """#.utf8))
        XCTAssertEqual(
            camelCase.verifiedImageURL?.absoluteString,
            "https://api.bainluck.com/api/containers/machinery-who-gets-engaged/card-art.jpg"
        )
        XCTAssertEqual(camelCase.imageAlt, "Stacked engagement ring and wedding bands")

        let insecureOrBlank = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-fed-and-macro",
          "form_id": "contender_spotlight",
          "kicker": "ECONOMICS · FEDERAL RESERVE",
          "title": "Fed Decision",
          "image_url": "http://api.bainluck.com/insecure.png",
          "image_alt": "   ",
          "rows": []
        }
        """#.utf8))
        XCTAssertNil(insecureOrBlank.verifiedImageURL, "Non-HTTPS image_url must be ignored")
        XCTAssertNil(insecureOrBlank.imageAlt)

        let absent = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-next-james-bond",
          "form_id": "sibling_fields_grid",
          "kicker": "ENTERTAINMENT · JAMES BOND",
          "title": "Next James Bond",
          "rows": []
        }
        """#.utf8))
        XCTAssertNil(absent.imageUrl)
        XCTAssertNil(absent.verifiedImageURL)
        XCTAssertNil(absent.imageAlt)
    }

    #if canImport(UIKit)
    func testCardHeroUsesExact2To1FitFrameForAnyAspectRatioAndLeavesNoImageUnchanged() throws {
        let img2to1URL = "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png"
        let img3to2URL = "https://api.bainluck.com/api/containers/machinery-who-gets-engaged/card-art.jpg"

        let mapImg = makeSolidImage(size: CGSize(width: 1080, height: 540), color: .systemBlue)
        let ringImg = makeSolidImage(size: CGSize(width: 1024, height: 683), color: .systemTeal)

        let rows: [[String: Any]] = [
            ["outcome_id": 1, "name": "Pittsburgh", "probability": 0.485, "rendered_percent": 49],
            ["outcome_id": 2, "name": "Minneapolis", "probability": 0.42, "rendered_percent": 42],
            ["outcome_id": 3, "name": "Milwaukee", "probability": 0.40, "rendered_percent": 40],
        ]

        func decodeCard(imageURL: String?) throws -> MachineryCardContract {
            var dict: [String: Any] = [
                "slug": "machinery-test-card",
                "form_id": "benchmark_strip",
                "kicker": "WEATHER · CHRISTMAS",
                "title": "Pittsburgh leads at 49%",
                "subtitle": "Chance of measurable snow on Christmas Day.",
                "section_count": 1,
                "item_count": 11,
                "item_noun": "cities",
                "rows": rows,
            ]
            if let imageURL {
                dict["image_url"] = imageURL
                dict["image_alt"] = "Test image"
            }
            let data = try JSONSerialization.data(withJSONObject: dict)
            return try JSONDecoder().decode(MachineryCardContract.self, from: data)
        }

        let cardNoImage = try decodeCard(imageURL: nil)
        let card2to1 = try decodeCard(imageURL: img2to1URL)
        let card3to2 = try decodeCard(imageURL: img3to2URL)

        let preloaded: [String: UIImage] = [
            img2to1URL: mapImg,
            img3to2URL: ringImg,
        ]

        func measureHeight(
            _ card: MachineryCardContract,
            size: DynamicTypeSize = .large
        ) -> CGFloat {
            let root = MachineryDiscoverCardView(card: card, onOpenContainer: { _, _ in })
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .environment(\.machineryPreloadedImages12288, preloaded)
            let host = hostForMeasurement(root, at: size)
            return host.sizeThatFits(in: CGSize(width: 390, height: 2400)).height
        }

        let hBaseline = measureHeight(cardNoImage)
        let hMap = measureHeight(card2to1)
        let hRing = measureHeight(card3to2)

        // Card outer padding = 16 each side (card width 358); card internal padding = 16 each side -> image width = 326.
        // A 2:1 frame inside 326 pt width is 163 pt tall + 10 pt VStack spacing = 173 pt delta.
        let expectedDelta: CGFloat = (390 - 32 - 32) / 2.0 + 10.0
        XCTAssertEqual(hMap - hBaseline, expectedDelta, accuracy: 2.0, "2:1 image should add exact 2:1 frame height + spacing")
        XCTAssertEqual(hRing - hBaseline, expectedDelta, accuracy: 2.0, "3:2 image must fit inside the exact same 2:1 frame height (centre-cropped inside exact 2:1 box)")
        XCTAssertEqual(hMap, hRing, accuracy: 1.0)

        // Also confirm AX5 renders cleanly with zero truncation dots.
        let axRoot = MachineryDiscoverCardView(card: card3to2, onOpenContainer: { _, _ in })
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(Color(white: 0.96))
            .environment(\.colorScheme, .light)
            .environment(\.machineryPreloadedImages12288, preloaded)
        let axHost = hostForMeasurement(axRoot, at: .accessibility5)
        axHost.overrideUserInterfaceStyle = .light
        let axFit = axHost.sizeThatFits(in: CGSize(width: 390, height: 2400))
        axHost.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: ceil(axFit.height) + 8))
        axHost.view.setNeedsLayout()
        axHost.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(bounds: axHost.view.bounds, format: fmt).image { ctx in
            if !axHost.view.drawHierarchy(in: axHost.view.bounds, afterScreenUpdates: true) {
                axHost.view.layer.render(in: ctx.cgContext)
            }
        }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let joined = lines.joined(separator: " ")
        let normalized = joined.lowercased().replacingOccurrences(of: "1 1", with: "11")
        XCTAssertTrue(
            normalized.contains("see all") && normalized.contains("11") && normalized.contains("cities"),
            "Missing CTA in AX5 render; got: \(joined)"
        )
        XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Unexpected ellipsis at AX5: \(lines)")
    }

    private func makeSolidImage(size: CGSize, color: UIColor) -> UIImage {
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        return UIGraphicsImageRenderer(size: size, format: fmt).image { ctx in
            color.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
        }
    }
    #endif
}
