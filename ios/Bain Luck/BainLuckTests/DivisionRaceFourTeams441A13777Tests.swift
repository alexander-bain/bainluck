import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// 441: A (#13777) — Division race cards render all four teams:
/// - `Eliminated` only for teams settled out (`settled_out: true`), never from a low number
/// - `No recent probability` for unpriced teams (`settled_out: false`, missing/null number)
/// - `<1%` with a faint sliver for any active division team strictly under `1%`
///   (overriding iPhone's 0.5% rule so `0.5%..<1%` matches the website's `<1%`)
/// - Never `"0%"`.
@MainActor
final class DivisionRaceFourTeams441A13777Tests: XCTestCase {
    func testDisplayRulesCoverAllFourDivisionStatesAndLeaveNonDivisionUntouched() {
        let live = MachineryOutcomeDisplay441A.describe(
            probability: 0.525, renderedPercent: 53, unflooredPercent: 53, settledOut: false
        )
        XCTAssertEqual(live, MachineryOutcomeDisplay441A(state: .live, label: "53%", barWidthPercent: 53, muted: false))

        for p in [0.01, 0.014] {
            let onePct = MachineryOutcomeDisplay441A.describe(
                probability: p, renderedPercent: 1, unflooredPercent: 1, settledOut: false
            )
            XCTAssertEqual(onePct, MachineryOutcomeDisplay441A(state: .live, label: "1%", barWidthPercent: 4, muted: false))
        }

        // Website rule: anything strictly below 1% (`< 0.01`) prints "<1%" with a faint sliver.
        for p in [0.0099, 0.005, 0.004, 0.0005] {
            let subOne = MachineryOutcomeDisplay441A.describe(
                probability: p, renderedPercent: 1, unflooredPercent: 0, settledOut: false
            )
            XCTAssertEqual(subOne, MachineryOutcomeDisplay441A(state: .subOnePercent, label: "<1%", barWidthPercent: 2, muted: true))
        }

        // Settled out prints "Eliminated" with empty track even if a residue price arrived.
        for residue in [nil, 0.0, 0.005] as [Double?] {
            let eliminated = MachineryOutcomeDisplay441A.describe(
                probability: residue, renderedPercent: residue == nil ? nil : 1, unflooredPercent: nil, settledOut: true
            )
            XCTAssertEqual(eliminated, MachineryOutcomeDisplay441A(state: .eliminated, label: "Eliminated", barWidthPercent: 0, muted: true))
        }

        // No number with settledOut: false prints "No recent probability" with empty track (never "0%").
        for missingProb in [nil, 0.0, -0.01, Double.nan] as [Double?] {
            let noNumber = MachineryOutcomeDisplay441A.describe(
                probability: missingProb, renderedPercent: nil, unflooredPercent: nil, settledOut: false
            )
            XCTAssertEqual(noNumber, MachineryOutcomeDisplay441A(state: .noRecentProbability, label: "No recent probability", barWidthPercent: 0, muted: true))
        }

        // Non-division cards omit `settled_out` (`nil`) and preserve today's exact `<0.5%` / `0.5%->1%` rules.
        let legacySubHalf = MachineryOutcomeDisplay441A.describe(
            probability: 0.004, renderedPercent: 1, unflooredPercent: 0, settledOut: nil,
            legacyProbability: 0.004, legacyRenderedPercent: 1
        )
        XCTAssertEqual(legacySubHalf, MachineryOutcomeDisplay441A(state: .live, label: "<1%", barWidthPercent: 4, muted: false))

        let legacy099 = MachineryOutcomeDisplay441A.describe(
            probability: 0.0099, renderedPercent: 1, unflooredPercent: 1, settledOut: nil,
            legacyProbability: 0.0099, legacyRenderedPercent: 1
        )
        XCTAssertEqual(legacy099, MachineryOutcomeDisplay441A(state: .live, label: "1%", barWidthPercent: 4, muted: false))
    }

    func testDecodesUnpricedOutcomesAcrossAllThreeAtlasContractLocations() throws {
        let json = """
        {
          "machinery_card": {
            "slug": "machinery-afc-west-duel",
            "form_id": "sibling_fields_grid",
            "kicker": "AFC WEST",
            "title": "AFC West Title Race",
            "subtitle": "All four AFC West teams in the division title race.",
            "footer": "Open container",
            "scale_ordered": false,
            "section_count": 2,
            "item_count": 4,
            "item_noun": "divisions",
            "rows": [
              {
                "market_id": 53675,
                "outcome_id": 846594,
                "name": "Denver Broncos",
                "probability": 0.525,
                "rendered_percent": 53,
                "unfloored_percent": 53,
                "settled_out": false
              },
              {
                "market_id": 53675,
                "outcome_id": 846593,
                "name": "Kansas City Chiefs",
                "probability": 0.0099,
                "rendered_percent": 1,
                "unfloored_percent": 1,
                "settled_out": false
              }
            ],
            "unpriced_outcomes": [
              {
                "market_id": 53675,
                "outcome_id": 846592,
                "name": "Los Angeles Chargers",
                "label": "Los Angeles Chargers",
                "probability": null,
                "rendered_percent": null,
                "unfloored_percent": null,
                "settled_out": false,
                "art": {"url": null, "kind": "monogram"}
              },
              {
                "market_id": 53675,
                "outcome_id": 846591,
                "name": "Las Vegas Raiders",
                "label": "Las Vegas Raiders",
                "probability": null,
                "rendered_percent": null,
                "unfloored_percent": null,
                "settled_out": true,
                "art": {"url": null, "kind": "monogram"}
              }
            ]
          },
          "roundup": {
            "kicker": "AFC WEST",
            "footer": "See all",
            "rows": [
              {
                "market_id": 53675,
                "outcome_id": 846594,
                "label": "Denver Broncos",
                "probability": 0.525,
                "rendered_percent": 53,
                "unfloored_percent": 53,
                "settled_out": false
              },
              {
                "market_id": 53675,
                "outcome_id": 846593,
                "label": "Kansas City Chiefs",
                "probability": 0.005,
                "rendered_percent": 1,
                "unfloored_percent": 0,
                "settled_out": false
              }
            ],
            "unpriced_outcomes": [
              {
                "market_id": 53675,
                "outcome_id": 846592,
                "name": "Los Angeles Chargers",
                "label": "Los Angeles Chargers",
                "probability": null,
                "rendered_percent": null,
                "unfloored_percent": null,
                "settled_out": false
              },
              {
                "market_id": 53675,
                "outcome_id": 846591,
                "name": "Las Vegas Raiders",
                "label": "Las Vegas Raiders",
                "probability": null,
                "rendered_percent": null,
                "unfloored_percent": null,
                "settled_out": true
              }
            ]
          },
          "visual_block": {
            "form_id": "sibling_fields_grid",
            "initial_visible_limit": 3,
            "items": [
              {
                "market_id": 53675,
                "title": "AFC West",
                "scale_ordered": false,
                "outcomes": [
                  {
                    "outcome_id": 846594,
                    "name": "Denver Broncos",
                    "probability": 0.525,
                    "rendered_percent": 53,
                    "unfloored_percent": 53,
                    "settled_out": false
                  },
                  {
                    "outcome_id": 846593,
                    "name": "Kansas City Chiefs",
                    "probability": 0.0099,
                    "rendered_percent": 1,
                    "unfloored_percent": 1,
                    "settled_out": false
                  }
                ],
                "unpriced_outcomes": [
                  {
                    "market_id": 53675,
                    "outcome_id": 846592,
                    "name": "Los Angeles Chargers",
                    "probability": null,
                    "rendered_percent": null,
                    "unfloored_percent": null,
                    "settled_out": false
                  },
                  {
                    "market_id": 53675,
                    "outcome_id": 846591,
                    "name": "Las Vegas Raiders",
                    "probability": null,
                    "rendered_percent": null,
                    "unfloored_percent": null,
                    "settled_out": true
                  }
                ]
              }
            ]
          }
        }
        """
        struct Payload: Decodable {
            let machineryCard: MachineryCardContract
            let roundup: FeedRoundupContract
            let visualBlock: MachineryVisualBlock
            enum CodingKeys: String, CodingKey {
                case machineryCard = "machinery_card"
                case roundup
                case visualBlock = "visual_block"
            }
        }

        let decoded = try JSONDecoder().decode(Payload.self, from: Data(json.utf8))
        XCTAssertEqual(decoded.machineryCard.displayOutcomeRows.count, 4)
        XCTAssertEqual(
            decoded.machineryCard.displayOutcomeRows.map(\.probabilityLabel),
            ["53%", "<1%", "No recent probability", "Eliminated"]
        )

        XCTAssertEqual(decoded.visualBlock.marketItems.first?.displayOutcomes.count, 4)
        XCTAssertEqual(
            decoded.visualBlock.marketItems.first?.displayOutcomes.map(\.probabilityLabel),
            ["53%", "<1%", "No recent probability", "Eliminated"]
        )

        let builtRoundup = try XCTUnwrap(
            DiscoverRoundupCardModel.build(title: "AFC West Title Race", contract: decoded.roundup)
        )
        XCTAssertEqual(builtRoundup.rows.count, 4)
        XCTAssertEqual(
            builtRoundup.rows.map(\.formattedPercentText),
            ["53%", "<1%", "No recent probability", "Eliminated"]
        )
        XCTAssertFalse(builtRoundup.rows.contains { $0.formattedPercentText == "0%" })

        // Control: non-division card with 4 priced rows still stays capped at <= 3 on outcomeRows.
        let nonDivisionCard = MachineryCardContract(
            slug: "non-division-card",
            formId: .contenderSpotlight,
            kicker: "TITLE",
            title: "Championship Race",
            outcomeRows: [
                MachineryOutcomeVisual(outcomeId: 1, name: "A", probability: 0.40, renderedPercent: 40),
                MachineryOutcomeVisual(outcomeId: 2, name: "B", probability: 0.30, renderedPercent: 30),
                MachineryOutcomeVisual(outcomeId: 3, name: "C", probability: 0.20, renderedPercent: 20),
                MachineryOutcomeVisual(outcomeId: 4, name: "D", probability: 0.10, renderedPercent: 10),
            ]
        )
        XCTAssertEqual(nonDivisionCard.outcomeRows.count, 3)
        XCTAssertEqual(nonDivisionCard.displayOutcomeRows.count, 3)
    }

    func testRendersDivisionRaceFourTeamsAt390And834LightAndDarkWithoutZeroPercent() throws {
        let outDir = ProcessInfo.processInfo.environment["DIV_RACE_441A_DIR"] ?? ""
        if !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let discoverCard = MachineryCardContract(
            slug: "machinery-afc-west-duel",
            formId: .siblingFieldsGrid,
            kicker: "AFC WEST",
            title: "AFC West Title Race",
            subtitle: "All four AFC West teams in the division title race.",
            footer: "See all 4 divisions",
            scaleOrdered: false,
            sectionCount: 2,
            outcomeRows: [
                MachineryOutcomeVisual(outcomeId: 846594, marketId: 53675, name: "Denver Broncos", probability: 0.525, renderedPercent: 53, unflooredPercent: 53, art: MachinerySubjectArt(kind: "monogram", accentColor: "#FB4F14", initials: "DEN"), settledOut: false),
                MachineryOutcomeVisual(outcomeId: 846593, marketId: 53675, name: "Kansas City Chiefs", probability: 0.0099, renderedPercent: 1, unflooredPercent: 1, art: MachinerySubjectArt(kind: "monogram", accentColor: "#E31837", initials: "KC"), settledOut: false),
            ],
            unpricedOutcomes: [
                MachineryOutcomeVisual(outcomeId: 846592, marketId: 53675, name: "Los Angeles Chargers", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#0080C6", initials: "LAC"), settledOut: false),
                MachineryOutcomeVisual(outcomeId: 846591, marketId: 53675, name: "Las Vegas Raiders", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#000000", initials: "LV"), settledOut: true),
            ]
        )

        let gridBlock = MachineryVisualBlock(
            formId: .siblingFieldsGrid,
            initialVisibleLimit: 3,
            itemNoun: "divisions",
            marketItems: [
                MachineryMarketVisualItem(
                    marketId: 53680,
                    title: "NFC South",
                    outcomes: [
                        MachineryOutcomeVisual(outcomeId: 11, name: "Tampa Bay Buccaneers", probability: 0.61, renderedPercent: 61, unflooredPercent: 61, art: MachinerySubjectArt(kind: "monogram", accentColor: "#D50A0A", initials: "TB"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 12, name: "Atlanta Falcons", probability: 0.38, renderedPercent: 38, unflooredPercent: 38, art: MachinerySubjectArt(kind: "monogram", accentColor: "#A71930", initials: "ATL"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 13, name: "Carolina Panthers", probability: 0.01, renderedPercent: 1, unflooredPercent: 1, art: MachinerySubjectArt(kind: "monogram", accentColor: "#0085CA", initials: "CAR"), settledOut: false),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(outcomeId: 14, name: "New Orleans Saints", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#D3BC8D", initials: "NO"), settledOut: true),
                    ]
                ),
                MachineryMarketVisualItem(
                    marketId: 53681,
                    title: "AFC South",
                    outcomes: [
                        MachineryOutcomeVisual(outcomeId: 21, name: "Houston Texans", probability: 0.57, renderedPercent: 57, unflooredPercent: 57, art: MachinerySubjectArt(kind: "monogram", accentColor: "#03202F", initials: "HOU"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 22, name: "Indianapolis Colts", probability: 0.42, renderedPercent: 42, unflooredPercent: 42, art: MachinerySubjectArt(kind: "monogram", accentColor: "#002C5F", initials: "IND"), settledOut: false),
                        MachineryOutcomeVisual(outcomeId: 23, name: "Jacksonville Jaguars", probability: 0.005, renderedPercent: 1, unflooredPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#006778", initials: "JAX"), settledOut: false),
                    ],
                    unpricedOutcomes: [
                        MachineryOutcomeVisual(outcomeId: 24, name: "Tennessee Titans", probability: 0, renderedPercent: 0, art: MachinerySubjectArt(kind: "monogram", accentColor: "#4B92DB", initials: "TEN"), settledOut: false),
                    ]
                ),
            ]
        )

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 834, height: 1080))
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let specs: [(name: String, width: CGFloat, height: CGFloat, scheme: ColorScheme, cols: Int)] = [
            ("render-390-light.png", 390, 1080, .light, 1),
            ("render-390-dark.png", 390, 1080, .dark, 1),
            ("render-834-light.png", 834, 720, .light, 2),
            ("render-834-dark.png", 834, 720, .dark, 2),
        ]

        let pinManager = PinManager(defaults: UserDefaults(suiteName: "test-13777-\(UUID().uuidString)")!, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()

        for spec in specs {
            let uiStyle: UIUserInterfaceStyle = spec.scheme == .dark ? .dark : .light
            let surface = NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        MachineryDiscoverCardView(card: discoverCard)
                        MachinerySectionBlockView(visualBlock: gridBlock, members: [], columnCount: spec.cols)
                    }
                    .padding(16)
                }
                .background(spec.scheme == .dark ? Color.black : DS.surface)
                .toolbar(.hidden, for: .navigationBar)
            }
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environment(\.horizontalSizeClass, spec.cols > 1 ? .regular : .compact)
            .environment(\.colorScheme, spec.scheme)
            .frame(width: spec.width, height: spec.height)
            .clipped()

            let host = hostForMeasurement(surface, at: .large)
            host.safeAreaRegions = []
            host.overrideUserInterfaceStyle = uiStyle
            host.traitOverrides.horizontalSizeClass = spec.cols > 1 ? .regular : .compact
            let bounds = CGRect(x: 0, y: 0, width: spec.width, height: spec.height)
            window.frame = bounds
            window.overrideUserInterfaceStyle = uiStyle
            window.rootViewController = host
            host.view.frame = bounds
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let img = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }

            if !outDir.isEmpty {
                try XCTUnwrap(img.pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent(spec.name),
                    options: .atomic
                )
            }

            let texts = try ocrStrings(img)
            let joined = texts.joined(separator: "\n")
            XCTAssertTrue(joined.contains("Denver Broncos"), "Missing Denver in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("Kansas City Chiefs"), "Missing Kansas City in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("Chargers"), "Missing Chargers in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("Las Vegas Raiders"), "Missing Raiders in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("<1%"), "Expected <1% for 0.99%/0.5% in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("No recent probability"), "Expected No recent probability in \(spec.name): \(joined)")
            XCTAssertTrue(joined.contains("Eliminated"), "Expected Eliminated in \(spec.name): \(joined)")
            XCTAssertFalse(texts.contains(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines) == "0%" }), "0% must never render in \(spec.name)")
            XCTAssertFalse(joined.contains("…"), "Unexpected ellipsis cutoff in \(spec.name): \(joined)")
        }
    }

    private func ocrStrings(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
}
