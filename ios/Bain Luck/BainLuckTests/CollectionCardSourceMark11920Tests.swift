import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class CollectionCardSourceMark11920Tests: XCTestCase {

    private func decodeFutures(_ json: String) throws -> FeedFuturesData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedFuturesData.self, from: Data(json.utf8))
    }

    func testCollectionCardSourceBadgeSaysCountInWordsAndNeverPrintsBothOrVenueName() throws {
        let bothWithoutCount = try decodeFutures(#"""
        {
          "id": 108620,
          "name": "Which party will control the Senate after the 2026 midterms?",
          "llm_sport_category": "politics",
          "source": "both",
          "status": "open",
          "top_outcomes": [
            {"id": 1, "name": "Republican", "probability": 0.54, "rendered_percent": 54},
            {"id": 2, "name": "Democratic", "probability": 0.46, "rendered_percent": 46}
          ]
        }
        """#)
        XCTAssertEqual(FuturesCardView.cardFaceSourceBadge(for: bothWithoutCount), "2 sources")

        let kalshiSingle = try decodeFutures(#"""
        {
          "id": 108631,
          "name": "Georgia Senate Election Winner",
          "llm_sport_category": "politics",
          "source": "kalshi",
          "source_count": 1,
          "status": "open",
          "top_outcomes": [
            {"id": 3, "name": "Jon Ossoff", "probability": 0.57, "rendered_percent": 57},
            {"id": 4, "name": "Republican nominee", "probability": 0.43, "rendered_percent": 43}
          ]
        }
        """#)
        XCTAssertNil(FuturesCardView.cardFaceSourceBadge(for: kalshiSingle))

        let polySingle = try decodeFutures(#"""
        {
          "id": 108632,
          "name": "Maine Senate Election Winner",
          "llm_sport_category": "politics",
          "source": "polymarket",
          "status": "open",
          "top_outcomes": [
            {"id": 5, "name": "Susan Collins", "probability": 0.61, "rendered_percent": 61}
          ]
        }
        """#)
        XCTAssertNil(FuturesCardView.cardFaceSourceBadge(for: polySingle))

        let datagolf = try decodeFutures(#"""
        {
          "id": 60393473,
          "name": "Masters Tournament - Winner",
          "llm_sport_category": "golf",
          "source": "datagolf",
          "status": "open",
          "top_outcomes": [
            {"id": 6, "name": "Scottie Scheffler", "probability": 0.21, "rendered_percent": 21}
          ]
        }
        """#)
        XCTAssertEqual(FuturesCardView.cardFaceSourceBadge(for: datagolf), "DataGolf")

        let withServedMark = try decodeFutures(#"""
        {
          "id": 108620,
          "name": "Which party will control the Senate after the 2026 midterms?",
          "llm_sport_category": "politics",
          "source": "both",
          "source_count": 2,
          "status": "open",
          "source_mark": {
            "state": "blend",
            "method": "Bain Luck blend",
            "sources": [
              {"key": "kalshi", "name": "Kalshi", "probability": 0.53, "observed_at": "2026-11-17T14:00:00Z"},
              {"key": "polymarket", "name": "Polymarket", "probability": 0.55, "observed_at": "2026-11-17T14:01:00Z"}
            ]
          },
          "top_outcomes": [
            {"id": 1, "name": "Republican", "probability": 0.54, "rendered_percent": 54},
            {"id": 2, "name": "Democratic", "probability": 0.46, "rendered_percent": 46}
          ]
        }
        """#)
        XCTAssertNil(FuturesCardView.cardFaceSourceBadge(for: withServedMark))
        XCTAssertEqual(withServedMark.sourceMark?.state, .blend)
        XCTAssertEqual(withServedMark.sourceMark?.sources.count, 2)
    }

    func testCollectionCardsRenderSourceMarkAndSheetAt390px() throws {
        let legacyBoth = try decodeFutures(#"""
        {
          "id": 108620,
          "name": "Which party will control the Senate after the 2026 midterms?",
          "llm_sport_category": "politics",
          "source": "both",
          "status": "open",
          "top_outcomes": [
            {"id": 1, "name": "Republican", "probability": 0.54, "rendered_percent": 54},
            {"id": 2, "name": "Democratic", "probability": 0.46, "rendered_percent": 46}
          ]
        }
        """#)

        let singleVenue = try decodeFutures(#"""
        {
          "id": 108631,
          "name": "Georgia Senate Election Winner",
          "llm_sport_category": "politics",
          "source": "kalshi",
          "source_count": 1,
          "status": "open",
          "top_outcomes": [
            {"id": 3, "name": "Jon Ossoff", "probability": 0.57, "rendered_percent": 57},
            {"id": 4, "name": "Republican nominee", "probability": 0.43, "rendered_percent": 43}
          ]
        }
        """#)

        let withServedMark = try decodeFutures(#"""
        {
          "id": 108621,
          "name": "Which party will control the House after the 2026 midterms?",
          "llm_sport_category": "politics",
          "source": "both",
          "source_count": 2,
          "status": "open",
          "top_outcomes": [
            {
              "id": 11,
              "name": "Democratic",
              "probability": 0.56,
              "rendered_percent": 56,
              "source_mark": {
                "state": "blend",
                "method": "Bain Luck blend",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.55, "observed_at": "2026-11-17T13:55:00Z"},
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.57, "observed_at": "2026-11-17T13:58:00Z"}
                ]
              }
            },
            {
              "id": 12,
              "name": "Republican",
              "probability": 0.44,
              "rendered_percent": 44,
              "source_mark": {
                "state": "blend",
                "method": "Bain Luck blend",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.45, "observed_at": "2026-11-17T13:55:00Z"},
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.43, "observed_at": "2026-11-17T13:58:00Z"}
                ]
              }
            }
          ]
        }
        """#)

        let pins = PinManager(
            defaults: UserDefaults(suiteName: "CollectionCardSourceMark11920Tests")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        func renderSlice<V: View>(_ content: V, fixedHeight: CGFloat? = nil) -> UIImage {
            let wrapped = content
                .environmentObject(pins)
                .frame(width: 390, alignment: .topLeading)
                .background(DS.surface)
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = .light
            let height: CGFloat
            if let fixedHeight {
                height = fixedHeight
            } else {
                let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 2200))
                height = ceil(fitting.height) + 16
            }
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: height))
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            let until = Date().addingTimeInterval(0.20)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
        }

        func cardShell(_ futures: FeedFuturesData) -> some View {
            FuturesCardView(futures: futures)
                .padding(14)
                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
        }

        let cardsSlice = renderSlice(
            VStack(alignment: .leading, spacing: 12) {
                Text("390 PX · COLLECTION CARDS (#11920)")
                    .font(.system(size: 11, weight: .bold))
                    .tracking(0.6)
                    .foregroundStyle(.secondary)
                cardShell(legacyBoth)
                cardShell(singleVenue)
                cardShell(withServedMark)
            }
            .padding(16)
        )

        let tapMark = try XCTUnwrap(withServedMark.topOutcomes?.first?.sourceMark)
        let sheetSlice = renderSlice(
            SourceMarkSheet(
                mark: tapMark,
                number: 0.56,
                now: ISO8601DateFormatter().date(from: "2026-11-17T14:00:00Z") ?? Date()
            ),
            fixedHeight: 340
        )

        // OCR on the card faces: "2 sources" appears in English; neither "both" nor "Kalshi"/"Polymarket" appears.
        let cardReq = VNRecognizeTextRequest()
        cardReq.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(cardsSlice.cgImage), options: [:]).perform([cardReq])
        let cardText = (cardReq.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
        XCTAssertTrue(cardText.contains("2 sources"), "Expected '2 sources' in OCR: \(cardText)")
        XCTAssertFalse(cardText.lowercased().contains("kalshi"), "Leaked Kalshi on card face: \(cardText)")
        XCTAssertFalse(cardText.lowercased().contains("polymarket"), "Leaked Polymarket on card face: \(cardText)")
        XCTAssertFalse(
            cardText.components(separatedBy: .whitespacesAndNewlines).contains { $0.lowercased() == "both" },
            "Leaked raw 'both' on card face: \(cardText)"
        )

        // OCR on the tap sheet: "Where this number comes from" + Kalshi & Polymarket prices.
        let sheetReq = VNRecognizeTextRequest()
        sheetReq.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(sheetSlice.cgImage), options: [:]).perform([sheetReq])
        let sheetText = (sheetReq.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
        XCTAssertTrue(sheetText.contains("Where this number comes from"), "Sheet title missing: \(sheetText)")
        XCTAssertTrue(sheetText.contains("Kalshi"), "Kalshi missing in sheet: \(sheetText)")
        XCTAssertTrue(sheetText.contains("Polymarket"), "Polymarket missing in sheet: \(sheetText)")

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_11920"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let totalH = cardsSlice.size.height + sheetSlice.size.height
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let combined = UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalH), format: fmt).image { _ in
                cardsSlice.draw(in: CGRect(x: 0, y: 0, width: 390, height: cardsSlice.size.height))
                sheetSlice.draw(in: CGRect(x: 0, y: cardsSlice.size.height, width: 390, height: sheetSlice.size.height))
            }
            if let png = combined.pngData() {
                try png.write(to: dirURL.appendingPathComponent("11920-collection-cards-source-mark-and-sheet-390.png"))
            }
        }
    }

    func testPairedMetricAndGroupingMachineryCollectionCardsDecodeAndRenderSourceMarks() throws {
        // Raw JSONDecoder (no convertFromSnakeCase) — verifies PairedCodingKey and SourceMark.Source.DynamicKey
        // decode both stage_1_source_mark / stage_2_source_mark and observed_at.
        let pairedJSON = #"""
        {
          "set_id": "oscars-best-picture-2027",
          "category": "entertainment",
          "kicker": "Oscars 2027",
          "title": "Best Picture",
          "subtitle": "Nominated and Wins side by side",
          "stage_1_label": "Nominated",
          "stage_2_label": "Wins",
          "stage_1_settled_yes_label": "✓ Nominated",
          "stage_1_settled_no_label": "Not nominated",
          "preferred_visual_form": "paired_bars_top5_expandable",
          "entries": [
            {
              "subject_key": "the-odyssey",
              "subject": "The Odyssey",
              "detail": "Christopher Nolan",
              "stage_1_market_id": 7001,
              "stage_1_probability": 0.91,
              "stage_1_source_mark": {
                "state": "blend",
                "method": "Bain Luck blend",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.90, "observed_at": "2026-11-20T16:50:00Z"},
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.92, "observed_at": "2026-11-20T16:52:00Z"}
                ]
              },
              "stage_2_market_id": 7002,
              "stage_2_probability": 0.34,
              "stage_2_source_mark": {
                "state": "single",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.34, "observed_at": "2026-11-20T16:55:00Z"}
                ]
              }
            },
            {
              "subject_key": "project-hail-mary",
              "subject": "Project Hail Mary",
              "detail": "Phil Lord & Christopher Miller",
              "stage_1_market_id": 7001,
              "stage_1_probability": 0.78,
              "stage_1_source_mark": {
                "state": "blend",
                "method": "Bain Luck blend",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.77, "observed_at": "2026-11-20T16:50:00Z"},
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.79, "observed_at": "2026-11-20T16:52:00Z"}
                ]
              },
              "stage_2_market_id": 7002,
              "stage_2_probability": 0.19,
              "stage_2_source_mark": {
                "state": "blend",
                "method": "Bain Luck blend",
                "sources": [
                  {"key": "kalshi", "name": "Kalshi", "probability": 0.18, "observed_at": "2026-11-20T16:50:00Z"},
                  {"key": "polymarket", "name": "Polymarket", "probability": 0.20, "observed_at": "2026-11-20T16:52:00Z"}
                ]
              }
            }
          ]
        }
        """#
        let pairedSet = try JSONDecoder().decode(PairedMetricSet.self, from: Data(pairedJSON.utf8))
        XCTAssertEqual(pairedSet.entries.count, 2)
        XCTAssertEqual(pairedSet.entries[0].stage1SourceMark?.state, .blend)
        XCTAssertEqual(pairedSet.entries[0].stage1SourceMark?.sources.first?.observedAt, "2026-11-20T16:50:00Z")
        XCTAssertEqual(pairedSet.entries[0].stage2SourceMark?.state, .single)
        XCTAssertNotNil(SourceMarkButton(pairedSet.entries[0].stage1SourceMark, number: 0.91, numberSize: 12, compactRow: true))
        XCTAssertNotNil(SourceMarkButton(pairedSet.entries[0].stage2SourceMark, number: 0.34, numberSize: 14, compactRow: true))

        // GroupingMachinery outcome & member fallback resolution (#12288 + #11920):
        let memberJSON = #"""
        {
          "type": "market",
          "id": 108621,
          "destination": {"kind": "market", "id": 108621, "web": "/futures/108621", "api": "/api/futures/108621"},
          "card": {
            "id": 108621,
            "name": "House Control 2026",
            "llm_sport_category": "politics",
            "source": "both",
            "source_count": 2,
            "status": "open",
            "top_outcomes": [
              {
                "id": 11,
                "name": "Democratic",
                "probability": 0.56,
                "rendered_percent": 56,
                "source_mark": {
                  "state": "blend",
                  "method": "Bain Luck blend",
                  "sources": [
                    {"key": "kalshi", "name": "Kalshi", "probability": 0.55, "observed_at": "2026-11-20T16:40:00Z"},
                    {"key": "polymarket", "name": "Polymarket", "probability": 0.57, "observed_at": "2026-11-20T16:41:00Z"}
                  ]
                }
              }
            ]
          }
        }
        """#
        let snakeDecoder = JSONDecoder()
        snakeDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let member = try snakeDecoder.decode(ContainerHubMember.self, from: Data(memberJSON.utf8))
        let visualWithoutDirectMark = MachineryOutcomeVisual(
            outcomeId: 11,
            marketId: 108621,
            name: "Democratic",
            probability: 0.56,
            renderedPercent: 56
        )
        let resolvedFromMember = MachinerySourceMarkResolver11920.outcomeMark(
            for: visualWithoutDirectMark,
            marketId: 108621,
            members: [member]
        )
        XCTAssertEqual(resolvedFromMember?.state, .blend)
        XCTAssertEqual(resolvedFromMember?.sources.count, 2)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let surface = scheme == .dark ? Color.black : DS.surface
            let wrapped = DiscoverPairedMetricCardView(set: pairedSet, form: .pairedBarsTop5Expandable)
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(surface)
                .environment(\.colorScheme, scheme)
            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 1600))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: ceil(fitting.height) + 8))
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = uiStyle
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            let until = Date().addingTimeInterval(0.15)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

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
            let ocr = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
            XCTAssertTrue(ocr.contains("The Odyssey"), "Missing contender on paired card (\(scheme)): \(ocr)")
            XCTAssertFalse(ocr.lowercased().contains("kalshi"), "Leaked Kalshi on paired card (\(scheme)): \(ocr)")
            XCTAssertFalse(ocr.lowercased().contains("polymarket"), "Leaked Polymarket on paired card (\(scheme)): \(ocr)")
            XCTAssertFalse(ocr.contains("…") || ocr.contains("..."), "Truncated text on paired card (\(scheme)): \(ocr)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_11920"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let suffix = scheme == .dark ? "dark" : "light"
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("11920-paired-collection-\(suffix)-390.png"))
                }
            }
        }
    }

    func testOwnerOnlyDevSourcesOverlayStaysHiddenFromPublicAndShowsBreadthOnlyWhenEnabled() throws {
        let suite = UserDefaults(suiteName: "DevSourcesOverlay11920Tests.\(UUID().uuidString)")!
        let publicUser = AuthUser(id: 999999, email: nil, displayName: "Reader", photoUrl: nil, onboardingCompleted: true, createdAt: nil)
        let ownerUser = AuthUser(id: GroupingMachineryGate12288.ownerUserId, email: nil, displayName: "Owner", photoUrl: nil, onboardingCompleted: true, createdAt: nil)

        XCTAssertFalse(DevSourcesOverlay11920.isSwitchEnabled(for: nil, defaults: suite))
        XCTAssertFalse(DevSourcesOverlay11920.isSwitchEnabled(for: publicUser, defaults: suite))
        XCTAssertFalse(DevSourcesOverlay11920.isSwitchEnabled(for: ownerUser, defaults: suite), "Owner dev overlay must default off")

        // Attempting to enable for non-owner or nil must be ignored.
        DevSourcesOverlay11920.setSwitchEnabled(true, for: nil, defaults: suite)
        DevSourcesOverlay11920.setSwitchEnabled(true, for: publicUser, defaults: suite)
        XCTAssertFalse(DevSourcesOverlay11920.isSwitchEnabled(for: publicUser, defaults: suite))

        // Enabling for owner turns it on only for owner.
        DevSourcesOverlay11920.setSwitchEnabled(true, for: ownerUser, defaults: suite)
        XCTAssertTrue(DevSourcesOverlay11920.isSwitchEnabled(for: ownerUser, defaults: suite))
        XCTAssertFalse(DevSourcesOverlay11920.isSwitchEnabled(for: publicUser, defaults: suite))

        let devMark = try JSONDecoder().decode(SourceMark.self, from: Data(#"""
        {
          "state": "blend",
          "method": "Bain Luck blend",
          "sources": [
            {"key": "kalshi", "name": "Kalshi", "probability": 0.55, "observed_at": "2026-11-20T16:40:00Z"},
            {"key": "polymarket", "name": "Polymarket", "probability": 0.57, "observed_at": "2026-11-20T16:41:00Z"}
          ],
          "dev": {
            "of": 3,
            "missing": ["odds_api"],
            "weights": {"kalshi": 0.5, "polymarket": 0.5}
          }
        }
        """#.utf8))
        XCTAssertEqual(DevSourcesOverlay11920.badgeText(for: devMark), "2/3")
        let lines = DevSourcesOverlay11920.sheetSummaryLines(for: devMark)
        XCTAssertTrue(lines.contains("Dev · 2 of 3 source families contributing"))
        XCTAssertTrue(lines.contains("Missing: Sportsbooks"))
        XCTAssertTrue(lines.contains("Weights: Kalshi 50% · Polymarket 50%"))
    }
}
