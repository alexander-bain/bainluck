import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13234 (1.0.7): A grouping card with a single section (`section_count: 1`,
/// e.g. Next James Bond, White Christmas, Who Gets Engaged) never says
/// `"Open all 1 sections"`. When the card carries the section's item count and
/// noun (`item_count` + `item_noun`), it says `"See all N <noun>"` (e.g.
/// `"See all 7 markets"`, `"See all 11 cities"`, `"See all 16 couples"`);
/// otherwise it says `"Open the full set"`. Multi-section sets keep
/// `"Open all N sections"`.
@MainActor
final class MachinerySingleSectionLabel13234Tests: XCTestCase {

    func testSingleSectionVsMultiSectionCallToActionAndRenderedCard() throws {
        // 1. Multi-section set keeps "Open all 4 sections"
        let multi = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-oscars-best-picture",
          "form_id": "paired_stage_bars",
          "kicker": "ENTERTAINMENT · OSCARS",
          "title": "Oscars Best Picture",
          "section_count": 4,
          "rows": []
        }
        """#.utf8))
        XCTAssertEqual(multi.openContainerCallToAction, "Open all 4 sections")

        // 2. Single-section set without count/noun (current live Next James Bond payload) -> "Open the full set"
        let bondWithoutNoun = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-next-james-bond",
          "form_id": "sibling_fields_grid",
          "kicker": "ENTERTAINMENT · JAMES BOND",
          "title": "Raye leads James Bond Theme at 47%, with Olivia Colman to play M at 29%",
          "section_count": 1,
          "rows": [
            {"outcome_id": 1, "name": "Raye · James Bond Theme", "probability": 0.47, "rendered_percent": 47},
            {"outcome_id": 2, "name": "Olivia Colman · M", "probability": 0.29, "rendered_percent": 29}
          ]
        }
        """#.utf8))
        XCTAssertEqual(bondWithoutNoun.openContainerCallToAction, "Open the full set")
        XCTAssertFalse(bondWithoutNoun.openContainerCallToAction.contains("1 sections"))

        // 3. Single-section set WITH count and noun -> "See all 7 markets" / "See all 11 cities" / "See all 16 couples"
        let bondWithNoun = try JSONDecoder().decode(MachineryCardContract.self, from: Data(#"""
        {
          "slug": "machinery-next-james-bond",
          "form_id": "sibling_fields_grid",
          "kicker": "ENTERTAINMENT · JAMES BOND",
          "title": "Raye leads James Bond Theme at 47%, with Olivia Colman to play M at 29%",
          "section_count": 1,
          "item_count": 7,
          "item_noun": "markets",
          "rows": [
            {"outcome_id": 1, "name": "Raye · James Bond Theme", "probability": 0.47, "rendered_percent": 47},
            {"outcome_id": 2, "name": "Olivia Colman · M", "probability": 0.29, "rendered_percent": 29}
          ]
        }
        """#.utf8))
        XCTAssertEqual(bondWithNoun.openContainerCallToAction, "See all 7 markets")

        #if canImport(UIKit)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let bg = scheme == .dark ? Color.black : Color(white: 0.96)
            let view = VStack(spacing: 14) {
                MachineryDiscoverCardView(card: bondWithoutNoun, onOpenContainer: { _, _ in })
                MachineryDiscoverCardView(card: bondWithNoun, onOpenContainer: { _, _ in })
            }
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)

            let host = hostForMeasurement(view, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let fit = host.sizeThatFits(in: CGSize(width: 390, height: 1200))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: max(400, ceil(fit.height) + 8)))
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
            let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = lines.joined(separator: " ")
            XCTAssertTrue(joined.contains("Open the full set"), "Expected 'Open the full set' (\(scheme)); got: \(joined)")
            XCTAssertTrue(joined.contains("See all 7 markets"), "Expected 'See all 7 markets' (\(scheme)); got: \(joined)")
            XCTAssertFalse(joined.contains("1 sections"), "Must never print 'Open all 1 sections' (\(scheme)); got: \(joined)")
            XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)); got: \(joined)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13234"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let tag = scheme == .dark ? "dark" : "light"
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("13234-single-section-set-\(tag)-390.png"))
                }
            }
        }
        #endif
    }
}
