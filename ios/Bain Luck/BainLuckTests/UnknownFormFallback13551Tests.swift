import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
private final class MockContainerHubService13551: ContainerHubLoading {
    let response: ContainerHubResponse

    init(response: ContainerHubResponse) {
        self.response = response
    }

    nonisolated func load(slug: String) async throws -> ContainerHubResponse {
        response
    }

    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
        []
    }
}
#endif

/// Item 3 + Ruling 366: B Add-on Item 2 (#13551):
/// An unknown `form_id`, unknown `kit_version`, unknown `layout`, or unknown `mark`
/// fails closed to `nil` (never silently coerced to `sibling_fields_grid`) and draws
/// today's standard grouped card / standard set-page cards with real rows and percents —
/// never an empty card and never `0%`.
@MainActor
final class UnknownFormFallback13551Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    // MARK: - 1. Discover card fail-closed fallback (unknown form_id, kit_version, layout, mark)

    func testUnknownFormAndKitVariantsDecodeNilAndRenderStandardGroupedCardWithRealPercents() throws {
        struct Variant {
            let name: String
            let machineryJSON: String
            let kitJSON: String
        }

        let variants: [Variant] = [
            Variant(
                name: "unknown_form_id",
                machineryJSON: """
                {
                  "slug": "machinery-next-james-bond",
                  "form_id": "made_up_casting_sheet_v9",
                  "kicker": "ENTERTAINMENT · JAMES BOND",
                  "title": "Raye leads James Bond Theme at 42%, with Margaret Qualley to play Bond girl at 31%",
                  "section_count": 1,
                  "rows": []
                }
                """,
                kitJSON: "null"
            ),
            Variant(
                name: "unknown_kit_version",
                machineryJSON: "null",
                kitJSON: """
                {
                  "kit_version": 99,
                  "layout": "grid",
                  "rows": [{"name": "Raye", "p": 42}]
                }
                """
            ),
            Variant(
                name: "unknown_kit_layout",
                machineryJSON: "null",
                kitJSON: """
                {
                  "kit_version": 1,
                  "layout": "polar_wheel_v2",
                  "rows": [{"name": "Raye", "p": 42}]
                }
                """
            ),
            Variant(
                name: "unknown_kit_mark",
                machineryJSON: "null",
                kitJSON: """
                {
                  "kit_version": 1,
                  "layout": "stack",
                  "rows": [
                    {
                      "name": "Raye",
                      "marks": [{"kind": "sankey_ribbon", "value": 42}]
                    }
                  ]
                }
                """
            )
        ]

        for variant in variants {
            let itemJSON = """
            {
              "type": "bundle",
              "score": 91.0,
              "data": {
                "bundle_id": "bundle-bond-\(variant.name)",
                "title": "Raye leads James Bond Theme at 42%, with Margaret Qualley to play Bond girl at 31%",
                "kind": "roundup",
                "collection_ref": {
                  "slug": "machinery-next-james-bond",
                  "name": "The Next James Bond Film",
                  "revision": 565166182,
                  "collection_count": 7
                },
                "roundup": {
                  "kicker": "ENTERTAINMENT · JAMES BOND",
                  "footer": "",
                  "rows": [
                    {"market_id": 108237, "outcome_id": 53022350, "label": "James Bond Theme · Raye", "probability": 0.42, "rendered_percent": 42},
                    {"market_id": 108238, "outcome_id": 53022351, "label": "Bond Girl · Margaret Qualley", "probability": 0.31, "rendered_percent": 31},
                    {"market_id": 108239, "outcome_id": 53022352, "label": "M · Olivia Colman", "probability": 0.29, "rendered_percent": 29}
                  ],
                  "machinery_card": \(variant.machineryJSON),
                  "kit_card": \(variant.kitJSON)
                },
                "items": []
              }
            }
            """
            let feedItem = try decoder().decode(FeedItem.self, from: Data(itemJSON.utf8))
            let bundle = try XCTUnwrap(feedItem.bundle, "Expected bundle for \(variant.name)")
            let contract = try XCTUnwrap(bundle.roundupContract, "Expected roundupContract for \(variant.name)")

            XCTAssertNil(contract.machineryCard, "[\(variant.name)] machineryCard must fail closed to nil (never coerce to sibling_fields_grid)")
            XCTAssertNil(contract.kitCard, "[\(variant.name)] kitCard must fail closed to nil")
            XCTAssertTrue(contract.hasUnknownLookFallback, "[\(variant.name)] must record unknown look fallback")
            XCTAssertTrue(bundle.admitsRoundupCard, "[\(variant.name)] Discover bundle must remain admitted")
            XCTAssertNil(DiscoverViewModel.suppressionReason(feedItem), "[\(variant.name)] DiscoverViewModel must not suppress unknown look bundle")

            let ref = try XCTUnwrap(bundle.roundupCollectionRef)
            let model = try XCTUnwrap(
                DiscoverRoundupCardModel.build(
                    title: bundle.title,
                    contract: contract,
                    fallbackKicker: ref.name,
                    fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: ref),
                    allowFlexibleRowCount: true
                ),
                "[\(variant.name)] expected standard grouped DiscoverRoundupCardModel"
            )
            XCTAssertEqual(model.rows.map(\.label), [
                "James Bond Theme · Raye",
                "Bond Girl · Margaret Qualley",
                "M · Olivia Colman"
            ])
            XCTAssertEqual(model.rows.map(\.formattedPercentText), ["42%", "31%", "29%"])
        }
    }

    func testUnknownLookWithEmptyRoundupRowsAndRealEventItemsAdmitsAndPreservesRealRows() throws {
        let itemJSON = """
        {
          "type": "bundle",
          "score": 88.0,
          "data": {
            "bundle_id": "bundle-slate-unknown",
            "title": "The closest games tonight",
            "kind": "roundup",
            "collection_ref": {
              "slug": "machinery-nba-night",
              "name": "NBA Tonight",
              "revision": 1001,
              "collection_count": 3
            },
            "roundup": {
              "kicker": "NBA · TONIGHT",
              "footer": "",
              "rows": [],
              "machinery_card": {
                "slug": "machinery-nba-night",
                "form_id": "unseen_slate_grid_2027",
                "kicker": "NBA · TONIGHT",
                "title": "The closest games tonight"
              }
            },
            "items": [
              {
                "type": "event",
                "score": 90.0,
                "data": {
                  "id": 15349574,
                  "sport": "basketball_nba",
                  "sport_name": "NBA",
                  "away_team": "Detroit Pistons",
                  "home_team": "Atlanta Hawks",
                  "status": "scheduled",
                  "current_odds": {"away_probability": 0.51, "home_probability": 0.49, "away_rendered_percent": 51, "home_rendered_percent": 49}
                }
              }
            ]
          }
        }
        """
        let feedItem = try decoder().decode(FeedItem.self, from: Data(itemJSON.utf8))
        let bundle = try XCTUnwrap(feedItem.bundle)
        XCTAssertNil(bundle.roundupContract?.machineryCard)
        XCTAssertTrue(bundle.admitsRoundupCard)
        XCTAssertNil(DiscoverViewModel.suppressionReason(feedItem))
    }

    // MARK: - 2. Set Page fail-closed fallback (unknown form_id, kit_version, layout, mark)

    func testUnknownSetPageVisualAndKitBlocksFallBackToStandardMemberCards() throws {
        let payloads: [(String, String)] = [
            ("unknown_visual_form_id", """
            "visual_block": {"form_id": "made_up_axis_2027", "items": []}
            """),
            ("unknown_kit_version", """
            "kit_block": {"kit_version": 42, "layout": "axis", "rows": [{"name": "A", "p": 55}]}
            """),
            ("unknown_kit_layout", """
            "kit_block": {"kit_version": 1, "layout": "radar_hexagon", "rows": [{"name": "A", "p": 55}]}
            """),
            ("unknown_kit_mark", """
            "kit_block": {"kit_version": 1, "layout": "grid", "cells": [{"mark_kind": "spark_cube", "label": "55%"}]}
            """)
        ]

        for (label, blockField) in payloads {
            let hubJSON = """
            {
              "state": "published",
              "slug": "machinery-next-james-bond",
              "revision": 565166182,
              "subtitle": "All seven Bond film races in one set.",
              "container": {
                "id": 2026,
                "kind": "roundup",
                "name": "The Next James Bond Film",
                "slug": "machinery-next-james-bond",
                "category": "entertainment",
                "status": "published"
              },
              "children": [],
              "sections": [
                {
                  "class": "cast_and_theme",
                  "title": "Bond Film Races",
                  "layout": "standard",
                  "count": 2,
                  \(blockField),
                  "members": [
                    {
                      "type": "market",
                      "id": 108237,
                      "destination": {"kind": "market", "id": 108237, "api": "/api/futures/108237", "web": "/futures/108237"},
                      "card": {
                        "id": 108237,
                        "name": "Artist performing the James Bond Theme?",
                        "category": "entertainment",
                        "market_tier": 2,
                        "status": "open",
                        "source": "polymarket",
                        "source_count": 2,
                        "outcome_count": 2,
                        "top_outcomes": [
                          {"id": 53022350, "name": "Raye", "probability": 0.42, "rendered_percent": 42, "rank": 1},
                          {"id": 53022351, "name": "Olivia Dean", "probability": 0.24, "rendered_percent": 24, "rank": 2}
                        ]
                      }
                    },
                    {
                      "type": "market",
                      "id": 108238,
                      "destination": {"kind": "market", "id": 108238, "api": "/api/futures/108238", "web": "/futures/108238"},
                      "card": {
                        "id": 108238,
                        "name": "Actress cast as Bond girl?",
                        "category": "entertainment",
                        "market_tier": 2,
                        "status": "open",
                        "source": "polymarket",
                        "source_count": 2,
                        "outcome_count": 2,
                        "top_outcomes": [
                          {"id": 53022360, "name": "Margaret Qualley", "probability": 0.31, "rendered_percent": 31, "rank": 1},
                          {"id": 53022361, "name": "Florence Pugh", "probability": 0.17, "rendered_percent": 17, "rank": 2}
                        ]
                      }
                    }
                  ]
                }
              ],
              "member_count": 2,
              "withheld": [],
              "withheld_count": 0,
              "assembled": true
            }
            """
            let hub = try decoder().decode(ContainerHubResponse.self, from: Data(hubJSON.utf8))
            let sec = try XCTUnwrap(hub.sections.first, "[\(label)] missing section")
            XCTAssertNil(sec.visualBlock, "[\(label)] visualBlock must fail closed to nil")
            XCTAssertNil(sec.kitBlock, "[\(label)] kitBlock must fail closed to nil")

            let presentation = ContainerHubPresentation(response: hub)
            XCTAssertFalse(presentation.hasMachinerySections, "[\(label)] must fall back to standard set-page presentation")
            XCTAssertEqual(presentation.displaySections.count, 1)
            XCTAssertEqual(presentation.displaySections.first?.members.count, 2)
            XCTAssertNil(presentation.displaySections.first?.visualBlock)
        }
    }

    // MARK: - 3. Rendered 390pt Light & Dark proof (Discover card + Set Page)

    func testRenderedUnknownFormFallbackDiscoverCardAndSetPageAt390LightAndDark() async throws {
        let feedItemJSON = """
        {
          "type": "bundle",
          "score": 91.0,
          "data": {
            "bundle_id": "bundle-bond-unknown-render",
            "title": "Raye leads James Bond Theme at 42%, with Margaret Qualley to play Bond girl at 31%",
            "kind": "roundup",
            "collection_ref": {
              "slug": "machinery-next-james-bond",
              "name": "The Next James Bond Film",
              "revision": 565166182,
              "collection_count": 7
            },
            "roundup": {
              "kicker": "ENTERTAINMENT · JAMES BOND",
              "footer": "",
              "rows": [
                {"market_id": 108237, "outcome_id": 53022350, "label": "James Bond Theme · Raye", "probability": 0.42, "rendered_percent": 42},
                {"market_id": 108238, "outcome_id": 53022351, "label": "Bond Girl · Margaret Qualley", "probability": 0.31, "rendered_percent": 31},
                {"market_id": 108239, "outcome_id": 53022352, "label": "M · Olivia Colman", "probability": 0.29, "rendered_percent": 29}
              ],
              "machinery_card": {
                "slug": "machinery-next-james-bond",
                "form_id": "casting_sheet_future_unseen",
                "kicker": "ENTERTAINMENT · JAMES BOND",
                "title": "Raye leads James Bond Theme at 42%, with Margaret Qualley to play Bond girl at 31%"
              },
              "kit_card": {
                "kit_version": 99,
                "layout": "polar_wheel",
                "rows": [{"name": "Raye", "marks": [{"kind": "sankey_ribbon", "value": 42}]}]
              }
            },
            "items": []
          }
        }
        """

        let hubJSON = """
        {
          "state": "published",
          "slug": "machinery-next-james-bond",
          "revision": 565166182,
          "subtitle": "Two Bond casting races falling back from unseen look to standard set cards.",
          "container": {
            "id": 2026,
            "kind": "roundup",
            "name": "The Next James Bond Film",
            "slug": "machinery-next-james-bond",
            "category": "entertainment",
            "status": "published"
          },
          "children": [],
          "sections": [
            {
              "class": "cast_and_theme",
              "title": "Bond Film Races",
              "layout": "standard",
              "count": 2,
              "visual_block": {"form_id": "made_up_axis_2027", "items": []},
              "kit_block": {"kit_version": 99, "layout": "polar_wheel", "rows": []},
              "members": [
                {
                  "type": "market",
                  "id": 108237,
                  "destination": {"kind": "market", "id": 108237, "api": "/api/futures/108237", "web": "/futures/108237"},
                  "card": {
                    "id": 108237,
                    "name": "Artist performing the James Bond Theme?",
                    "category": "entertainment",
                    "market_tier": 2,
                    "status": "open",
                    "source": "polymarket",
                    "source_count": 2,
                    "outcome_count": 2,
                    "top_outcomes": [
                      {"id": 53022350, "name": "Raye", "probability": 0.42, "rendered_percent": 42, "rank": 1},
                      {"id": 53022351, "name": "Olivia Dean", "probability": 0.24, "rendered_percent": 24, "rank": 2}
                    ]
                  }
                },
                {
                  "type": "market",
                  "id": 108238,
                  "destination": {"kind": "market", "id": 108238, "api": "/api/futures/108238", "web": "/futures/108238"},
                  "card": {
                    "id": 108238,
                    "name": "Actress cast as Bond girl?",
                    "category": "entertainment",
                    "market_tier": 2,
                    "status": "open",
                    "source": "polymarket",
                    "source_count": 2,
                    "outcome_count": 2,
                    "top_outcomes": [
                      {"id": 53022360, "name": "Margaret Qualley", "probability": 0.31, "rendered_percent": 31, "rank": 1},
                      {"id": 53022361, "name": "Florence Pugh", "probability": 0.17, "rendered_percent": 17, "rank": 2}
                    ]
                  }
                }
              ]
            }
          ],
          "member_count": 2,
          "withheld": [],
          "withheld_count": 0,
          "assembled": true
        }
        """

        let feedItem = try decoder().decode(FeedItem.self, from: Data(feedItemJSON.utf8))
        let bundle = try XCTUnwrap(feedItem.bundle)
        let ref = try XCTUnwrap(bundle.roundupCollectionRef)
        let contract = try XCTUnwrap(bundle.roundupContract)
        let model = try XCTUnwrap(DiscoverRoundupCardModel.build(
            title: bundle.title,
            contract: contract,
            fallbackKicker: ref.name,
            fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: ref),
            allowFlexibleRowCount: true
        ))
        let hubResponse = try decoder().decode(ContainerHubResponse.self, from: Data(hubJSON.utf8))
        let service = MockContainerHubService13551(response: hubResponse)

        #if canImport(UIKit)
        let exportDir = ProcessInfo.processInfo.environment["EXPORT_UNKNOWN_FORM_13551_DIR"]
        for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let discoverCardImg = await renderInWindow(width: 390, height: 520, scheme: scheme) {
                VStack(alignment: .leading, spacing: 12) {
                    DiscoverRoundupCardView(model: model, collectionRef: ref, onOpenCollection: { _ in })
                }
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
            }
            let discoverOCR = recognizeText(in: discoverCardImg)
            XCTAssertTrue(discoverOCR.contains("Raye"), "Discover fallback missing Raye (\(suffix)): \(discoverOCR)")
            XCTAssertTrue(discoverOCR.contains("42%"), "Discover fallback missing 42% (\(suffix)): \(discoverOCR)")
            XCTAssertTrue(discoverOCR.contains("31%"), "Discover fallback missing 31% (\(suffix)): \(discoverOCR)")
            XCTAssertFalse(discoverOCR.contains("0%"), "Discover fallback must never show 0% (\(suffix)): \(discoverOCR)")
            XCTAssertFalse(discoverOCR.contains("…"), "Zero ellipsis (\(suffix)): \(discoverOCR)")

            let setPageImg = await renderInWindow(width: 390, height: 740, scheme: scheme) {
                NavigationStack {
                    ContainerHubView(slug: "machinery-next-james-bond", displayName: "The Next James Bond Film", service: service)
                        .navigationBarTitleDisplayMode(.inline)
                }
            }
            let setOCR = recognizeText(in: setPageImg)
            XCTAssertTrue(setOCR.contains("Bond Film Races"), "Set page missing section title (\(suffix)): \(setOCR)")
            XCTAssertTrue(setOCR.contains("Raye"), "Set page missing Raye (\(suffix)): \(setOCR)")
            XCTAssertTrue(setOCR.contains("42%"), "Set page missing 42% (\(suffix)): \(setOCR)")
            XCTAssertTrue(setOCR.contains("31%"), "Set page missing 31% (\(suffix)): \(setOCR)")
            XCTAssertFalse(setOCR.contains("0%"), "Set page must never show 0% (\(suffix)): \(setOCR)")
            XCTAssertFalse(setOCR.contains("Loading"), "Set page stuck loading (\(suffix)): \(setOCR)")

            if let exportDir, !exportDir.isEmpty {
                let dir = URL(fileURLWithPath: exportDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                try discoverCardImg.pngData()?.write(to: dir.appendingPathComponent("unknown-form-discover-\(suffix)-390.png"))
                try setPageImg.pngData()?.write(to: dir.appendingPathComponent("unknown-form-setpage-\(suffix)-390.png"))
            }
        }
        #endif
    }

    func testStandardGameRowShowsTeamNamesBesidePercentsInLightAndDark() async throws {
        let gameJSON = """
        [
          {
            "type": "event",
            "score": 92.0,
            "data": {
              "id": 1357901,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "away_team": "Miami Heat",
              "home_team": "Boston Celtics",
              "away_team_data": {"team_id": 14, "slug": "miami-heat", "abbreviation": "MIA"},
              "home_team_data": {"team_id": 2, "slug": "boston-celtics", "abbreviation": "BOS"},
              "status": "scheduled",
              "current_odds": {
                "away_probability": 0.36,
                "home_probability": 0.64,
                "away_rendered_percent": 36,
                "home_rendered_percent": 64
              }
            }
          },
          {
            "type": "event",
            "score": 90.0,
            "data": {
              "id": 1357902,
              "sport": "basketball_ncaab",
              "sport_name": "CBB",
              "away_team": "SE Louisiana",
              "home_team": "N Colorado",
              "status": "live",
              "away_score": 48,
              "home_score": 45,
              "current_odds": {
                "away_probability": 0.391,
                "home_probability": 0.609
              }
            }
          },
          {
            "type": "event",
            "score": 88.0,
            "data": {
              "id": 1357903,
              "sport": "tennis_atp",
              "sport_name": "ATP",
              "away_team": "Krawietz / Puetz",
              "home_team": "Granollers / Zeballos",
              "status": "scheduled",
              "current_odds": {
                "away_probability": 0.54,
                "home_probability": 0.46,
                "away_rendered_percent": 54,
                "home_rendered_percent": 46
              }
            }
          }
        ]
        """
        let gameItems = try decoder().decode([FeedItem].self, from: Data(gameJSON.utf8))
        XCTAssertEqual(gameItems.count, 3)

        #if canImport(UIKit)
        let exportDir = ProcessInfo.processInfo.environment["EXPORT_13637_GAMEROW_DIR"]
        for (sizeLabel, dynamicType) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let (img, measuredSize) = await renderIntrinsicInWindow(width: 390, scheme: scheme, dynamicType: dynamicType) {
                    NativeGroupCard(
                        title: "Matchups",
                        items: gameItems,
                        kind: "sports",
                        navigationPath: .constant(NavigationPath())
                    )
                    .padding(16)
                }
                XCTAssertLessThanOrEqual(
                    measuredSize.width,
                    390.5,
                    "Game row spilled past 390pt card bounds (\(sizeLabel), \(suffix)): \(measuredSize.width)"
                )
                let ocr = recognizeText(in: img).replacingOccurrences(of: " | ", with: " ")
                var ocrNorm = ocr
                    .replacingOccurrences(of: "/", with: " ")
                    .replacingOccurrences(of: "\u{00A0}", with: " ")
                while ocrNorm.contains("  ") {
                    ocrNorm = ocrNorm.replacingOccurrences(of: "  ", with: " ")
                }
                for expected in [
                    "MIA 36%", "BOS 64%",
                    "SE", "Louisiana", "39.1%", "N", "Colorado", "60.9%",
                    "Krawietz", "Puetz 54%", "Granollers", "Zeballos 46%"
                ] {
                    XCTAssertTrue(
                        ocrNorm.localizedCaseInsensitiveContains(expected),
                        "Game row missing '\(expected)' (\(sizeLabel), \(suffix)): \(ocr)"
                    )
                }
                XCTAssertFalse(ocr.contains(" at "), "Drop duplicate 'X at Y' title when odds are present (\(sizeLabel), \(suffix)): \(ocr)")
                XCTAssertFalse(ocr.contains("…") || ocr.contains("..."), "Zero ellipsis on game row (\(sizeLabel), \(suffix)): \(ocr)")

                if let exportDir, !exportDir.isEmpty {
                    let dir = URL(fileURLWithPath: exportDir, isDirectory: true)
                    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                    try img.pngData()?.write(to: dir.appendingPathComponent("gamerow-\(sizeLabel)-\(suffix)-390.png"))
                }
            }
        }
        #endif
    }

    #if canImport(UIKit)
    private func renderIntrinsicInWindow<V: View>(
        width: CGFloat,
        scheme: ColorScheme,
        dynamicType: DynamicTypeSize,
        @ViewBuilder content: () -> V
    ) async -> (UIImage, CGSize) {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let root = content()
            .frame(width: width, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())
            .environmentObject(AuthManager())

        let host = hostForMeasurement(root, at: dynamicType)
        host.overrideUserInterfaceStyle = style
        let measured = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
        let height = max(240, ceil(measured.height))
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: rect)
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<12 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 35_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
        return (img, measured)
    }
    private func renderInWindow<V: View>(
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        @ViewBuilder content: () -> V
    ) async -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let root = content()
            .frame(width: width, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.dynamicTypeSize, .large)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())
            .environmentObject(AuthManager())

        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = style
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: rect)
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<12 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 40_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }
    #endif
}
