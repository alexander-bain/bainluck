import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// Ruling `366: B` / `363: A` (`#13551`):
/// Verifies the off-by-default Discover Kit stand-in switch (`KitCardStandInSwitch366B`):
/// - Switch OFF (default in Debug, always OFF in Release): draws today's standard grouped card.
/// - Switch ON + valid `kit_card`: `KitCardView366B` stands in for today's card and routes cleanly.
/// - Switch ON + refused/unsupported `kit_card`: fails closed and draws today's card with real percents.
@MainActor
final class KitCardStandInSwitch366BTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func validStackKitCardJSON() -> String {
        """
        {
          "kit_version": 1,
          "id": "kit-bond-standin-test",
          "layout": "stack",
          "variant": "one_in_n",
          "kicker": "KIT V1 · STAND-IN PREVIEW",
          "common_headline": "Kit Card Stand-In Active",
          "stat_caption": "Raye leads James Bond Theme at 42% when the stand-in switch is enabled.",
          "source_mark": {
            "label": "2 sources",
            "count": 2
          },
          "route": {
            "kind": "collection",
            "id": null,
            "slug": "machinery-next-james-bond"
          },
          "footnote": "366: B stand-in preview; hidden when switch is off.",
          "disclosure": "2 more in this set",
          "refusal_reason": null,
          "body": {
            "items": [
              {
                "id": "bond-raye",
                "marks": [
                  {
                    "mark": "word",
                    "text": "Raye · James Bond Theme",
                    "style": "row",
                    "tone": "primary",
                    "align": "left",
                    "width": "flex",
                    "bold": true
                  },
                  {
                    "mark": "bar",
                    "bar_style": "single",
                    "fill": 0.42,
                    "fill_color": {"light": "#008348", "dark": "#269663"}
                  },
                  {
                    "mark": "number",
                    "value": 42,
                    "display": "42%",
                    "unit": "%",
                    "tone": "primary",
                    "align": "right",
                    "width": "sm"
                  }
                ]
              },
              {
                "id": "bond-qualley",
                "marks": [
                  {
                    "mark": "word",
                    "text": "Margaret Qualley · Bond Girl",
                    "style": "row",
                    "tone": "primary",
                    "align": "left",
                    "width": "flex",
                    "bold": false
                  },
                  {
                    "mark": "bar",
                    "bar_style": "single",
                    "fill": 0.31,
                    "fill_color": {"light": "#2563EB", "dark": "#60A5FA"}
                  },
                  {
                    "mark": "number",
                    "value": 31,
                    "display": "31%",
                    "unit": "%",
                    "tone": "primary",
                    "align": "right",
                    "width": "sm"
                  }
                ]
              }
            ]
          }
        }
        """
    }

    private func makeRoundupFeedItemJSON(kitCardJSON: String) -> String {
        """
        {
          "type": "bundle",
          "score": 91.0,
          "data": {
            "bundle_id": "bundle-bond-kit-switch",
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
              "machinery_card": null,
              "kit_card": \(kitCardJSON)
            },
            "items": []
          }
        }
        """
    }

    // MARK: - 1. Switch defaults OFF and Release build cannot expose Kit cards to readers

    func testSwitchDefaultsOffAndReleaseBuildCannotEnableIt() throws {
        XCTAssertFalse(KitCardStandInSwitch366B.defaultEnabled, "Kit stand-in switch must default to OFF")
        XCTAssertFalse(KitCardStandInSwitch366B.isEnabled, "Default Debug/test environment must keep switch OFF")

        let item = try decoder().decode(FeedItem.self, from: Data(makeRoundupFeedItemJSON(kitCardJSON: validStackKitCardJSON()).utf8))
        let bundle = try XCTUnwrap(item.bundle)
        let contract = try XCTUnwrap(bundle.roundupContract)
        XCTAssertNotNil(contract.kitCard, "Envelope validation from #13579 remains single source of truth")
        XCTAssertNil(contract.kitCardSpec, "With switch OFF, FeedRoundupContract skips full KitV1CardSpec decode")
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: contract),
            .standardCard,
            "With switch OFF, Discover must render today's standard card (never KitCardView366B)"
        )

        // Structural Release-isolation & UI-surface guard
        let testFile = URL(fileURLWithPath: #filePath)
        let iosRoot = testFile.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let switchSource = try String(contentsOf: iosRoot.appendingPathComponent("Utilities/KitCardStandInSwitch366B.swift"))
        XCTAssertTrue(switchSource.contains("#else\n        return defaultEnabled"), "Release builds must return defaultEnabled (false)")
        XCTAssertFalse(switchSource.contains("UserDefaults"), "Off-by-default 366:B stand-in switch must not persist UserDefaults toggles yet")
        XCTAssertFalse(switchSource.contains("@AppStorage"))

        let discoverSource = try String(contentsOf: iosRoot.appendingPathComponent("Views/DiscoverView.swift"))
        let kitCallSites = discoverSource.components(separatedBy: "KitCardView366B(").count - 1
        XCTAssertEqual(kitCallSites, 1, "DiscoverView must have exactly one KitCardView366B entry point behind KitCardStandInSwitch366B")
        XCTAssertTrue(discoverSource.contains("KitCardStandInSwitch366B.resolveDiscoverStandIn"))
        guard let switchFirstRange = discoverSource.range(of: "} else if KitCardStandInSwitch366B.isEnabled,"),
              let kitResolveRange = discoverSource.range(of: "KitCardStandInSwitch366B.resolveDiscoverStandIn") else {
            return XCTFail("Expected DiscoverView to gate kit stand-in with KitCardStandInSwitch366B.isEnabled first")
        }
        XCTAssertLessThan(
            switchFirstRange.lowerBound,
            kitResolveRange.lowerBound,
            "DiscoverView must check KitCardStandInSwitch366B.isEnabled before calling resolveRoundupBundle"
        )

        let prefsSource = try String(contentsOf: iosRoot.appendingPathComponent("Views/PreferencesView.swift"))
        XCTAssertFalse(prefsSource.contains("KitCardStandInSwitch366B"), "PreferencesView must not expose a Kit toggle before 363:A blind grading")
        XCTAssertFalse(prefsSource.contains("BainLuckEnableKitCardsPreview"))
    }

    // MARK: - 2. Switch ON renders Kit stand-in and maps all 4 route kinds

    func testSwitchOnStandsInValidKitCardAndMapsAllFourRouteKinds() throws {
        let rawData = Data(makeRoundupFeedItemJSON(kitCardJSON: validStackKitCardJSON()).utf8)
        let item = try KitCardStandInSwitch366B.withOverrideForTesting(true) {
            try decoder().decode(FeedItem.self, from: rawData)
        }
        let bundle = try XCTUnwrap(item.bundle)
        let contract = try XCTUnwrap(bundle.roundupContract)
        let ref = try XCTUnwrap(bundle.roundupCollectionRef)

        KitCardStandInSwitch366B.withOverrideForTesting(true) {
            XCTAssertTrue(KitCardStandInSwitch366B.isEnabled)
            guard case .kit(let spec) = KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: contract) else {
                return XCTFail("Expected .kit resolution when stand-in switch is ON and spec is valid")
            }
            XCTAssertEqual(spec.id, "kit-bond-standin-test")

            KitCardStandInSwitch366B.withOverrideForTesting(false) {
                XCTAssertEqual(KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: contract), .standardCard)
            }
            XCTAssertTrue(KitCardStandInSwitch366B.isEnabled)
        }
        XCTAssertFalse(KitCardStandInSwitch366B.isEnabled, "Scoped override must restore OFF state after exiting")

        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: "machinery-next-james-bond"),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            ),
            .containerHub(slug: "machinery-next-james-bond", name: "The Next James Bond Film")
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: "custom-kit-set"),
                fallbackCollectionRef: ref,
                fallbackTitle: "Custom Set Title"
            ),
            .containerHub(slug: "custom-kit-set", name: "Custom Set Title")
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: "custom-kit-set"),
                fallbackCollectionRef: nil,
                fallbackTitle: "   ",
                kitCardHeadline: "Big Kit Headline"
            ),
            .containerHub(slug: "custom-kit-set", name: "Big Kit Headline"),
            "Empty card title must fall back to the kit card's own big line, never raw slug"
        )
        XCTAssertNil(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: "never-use-slug-as-title"),
                fallbackCollectionRef: nil,
                fallbackTitle: "   ",
                kitCardHeadline: "   "
            ),
            "Must never use raw slug as page title when both title and kit headline are empty"
        )
        XCTAssertNil(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: "never-use-slug-as-title"),
                fallbackCollectionRef: nil,
                fallbackTitle: "",
                kitCardHeadline: nil
            ),
            "Must never use raw slug as page title when headline is nil"
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .collection, id: nil, slug: " "),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            ),
            .containerHub(slug: "machinery-next-james-bond", name: "The Next James Bond Film")
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .event, id: 98765, slug: nil),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            ),
            .eventDetail(id: 98765)
        )
        XCTAssertNil(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .event, id: 0, slug: nil),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            )
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .market, id: 108237, slug: nil),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            ),
            .futuresDetail(id: 108237)
        )
        XCTAssertNil(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .market, id: -1, slug: nil),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            )
        )
        XCTAssertEqual(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .team, id: nil, slug: "usa"),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            ),
            .teamDetail(slug: "usa")
        )
        XCTAssertNil(
            KitCardStandInSwitch366B.resolveRoute(
                KitV1Route(kind: .team, id: nil, slug: "  "),
                fallbackCollectionRef: ref,
                fallbackTitle: bundle.title
            )
        )
    }

    // MARK: - 3. Switch ON + refused / unsupported Kit card falls back cleanly to today's card

    func testSwitchOnWithRefusedOrUnsupportedKitCardFallsBackToStandardCard() throws {
        let unsupportedCases: [(String, String)] = [
            ("refusal_reason", """
            {
              "kit_version": 1,
              "id": "kit-refused-pictures",
              "layout": "stack",
              "refusal_reason": "missing portrait art",
              "body": {
                "items": [{"id": "r1", "marks": [{"mark": "word", "text": "Raye"}]}]
              }
            }
            """),
            ("fallback_today", """
            {
              "kit_version": 1,
              "id": "kit-explicit-fallback",
              "layout": "stack",
              "fallback_today": true,
              "body": {
                "items": [{"id": "r1", "marks": [{"mark": "word", "text": "Raye"}]}]
              }
            }
            """),
            ("unsupported_kit_version", """
            {
              "kit_version": 2,
              "id": "kit-v2-future",
              "layout": "stack",
              "body": {
                "items": [{"id": "r1", "marks": [{"mark": "word", "text": "Raye"}]}]
              }
            }
            """),
            ("unsupported_bar_style", """
            {
              "kit_version": 1,
              "id": "kit-stacked3",
              "layout": "stack",
              "body": {
                "items": [
                  {
                    "id": "r1",
                    "marks": [
                      {"mark": "word", "text": "Raye"},
                      {"mark": "bar", "bar_style": "stacked3", "fill": 0.42, "fill_color": {"light": "#008348", "dark": "#269663"}}
                    ]
                  }
                ]
              }
            }
            """)
        ]

        try KitCardStandInSwitch366B.withOverrideForTesting(true) {
            for (name, kitJSON) in unsupportedCases {
                let item = try decoder().decode(FeedItem.self, from: Data(makeRoundupFeedItemJSON(kitCardJSON: kitJSON).utf8))
                let bundle = try XCTUnwrap(item.bundle, "[\(name)] expected bundle")
                let contract = try XCTUnwrap(bundle.roundupContract, "[\(name)] expected contract")
                let ref = try XCTUnwrap(bundle.roundupCollectionRef)

                XCTAssertNil(contract.kitCardSpec, "[\(name)] kitCardSpec must fail closed to nil")
                XCTAssertEqual(
                    KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: contract),
                    .standardCard,
                    "[\(name)] must fall back to today's standard card even with switch ON"
                )
                let fallbackModel = try XCTUnwrap(
                    DiscoverRoundupCardModel.build(
                        title: bundle.title,
                        contract: contract,
                        fallbackKicker: ref.name,
                        fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: ref),
                        allowFlexibleRowCount: true
                    )
                )
                XCTAssertEqual(fallbackModel.rows.map(\.formattedPercentText), ["42%", "31%", "29%"])
            }
        }
    }

    // MARK: - 4. 390pt Light & Dark Render Comparison (OFF vs ON vs Refused Fallback)

    func testRenderStandInSwitchOffOnAndRefusedAt390LightAndDark() async throws {
        let validRaw = Data(makeRoundupFeedItemJSON(kitCardJSON: validStackKitCardJSON()).utf8)
        let offItem = try KitCardStandInSwitch366B.withOverrideForTesting(false) {
            try decoder().decode(FeedItem.self, from: validRaw)
        }
        let offBundle = try XCTUnwrap(offItem.bundle)
        let offContract = try XCTUnwrap(offBundle.roundupContract)
        let offRef = try XCTUnwrap(offBundle.roundupCollectionRef)
        XCTAssertNil(offContract.kitCardSpec, "Switch OFF skips KitV1CardSpec decode")

        let validItem = try KitCardStandInSwitch366B.withOverrideForTesting(true) {
            try decoder().decode(FeedItem.self, from: validRaw)
        }
        let validBundle = try XCTUnwrap(validItem.bundle)
        let validContract = try XCTUnwrap(validBundle.roundupContract)

        let refusedJSON = """
        {
          "kit_version": 1,
          "id": "kit-refused-render",
          "layout": "stack",
          "refusal_reason": "incomplete visual fit",
          "body": {
            "items": [{"id": "r1", "marks": [{"mark": "word", "text": "Raye"}]}]
          }
        }
        """
        let refusedItem = try KitCardStandInSwitch366B.withOverrideForTesting(true) {
            try decoder().decode(FeedItem.self, from: Data(makeRoundupFeedItemJSON(kitCardJSON: refusedJSON).utf8))
        }
        let refusedBundle = try XCTUnwrap(refusedItem.bundle)
        let refusedContract = try XCTUnwrap(refusedBundle.roundupContract)
        let refusedRef = try XCTUnwrap(refusedBundle.roundupCollectionRef)

        let offResolution = KitCardStandInSwitch366B.withOverrideForTesting(false) {
            KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: offContract)
        }
        let onResolution = KitCardStandInSwitch366B.withOverrideForTesting(true) {
            KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: validContract)
        }
        let refusedResolution = KitCardStandInSwitch366B.withOverrideForTesting(true) {
            KitCardStandInSwitch366B.resolveDiscoverStandIn(contract: refusedContract)
        }

        XCTAssertEqual(offResolution, .standardCard)
        guard case .kit(let activeKitSpec) = onResolution else {
            return XCTFail("Expected .kit resolution when stand-in switch is ON")
        }
        XCTAssertEqual(refusedResolution, .standardCard)

        let offStandardModel = try XCTUnwrap(DiscoverRoundupCardModel.build(
            title: offBundle.title,
            contract: offContract,
            fallbackKicker: offRef.name,
            fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: offRef),
            allowFlexibleRowCount: (offContract.hasUnknownLookFallback || offContract.kitCard != nil)
        ))
        let refusedStandardModel = try XCTUnwrap(DiscoverRoundupCardModel.build(
            title: refusedBundle.title,
            contract: refusedContract,
            fallbackKicker: refusedRef.name,
            fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: refusedRef),
            allowFlexibleRowCount: (refusedContract.hasUnknownLookFallback || refusedContract.kitCard != nil)
        ))

        #if canImport(UIKit)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let bg = scheme == .dark ? Color.black : Color(white: 0.96)

            let columnView = VStack(alignment: .leading, spacing: 14) {
                sectionHeader("1. Switch OFF (default) -> Today's card", scheme: scheme)
                DiscoverRoundupCardView(model: offStandardModel, collectionRef: offRef)

                sectionHeader("2. Switch ON + valid kit_card -> Kit stand-in", scheme: scheme)
                KitCardView366B(spec: activeKitSpec)

                sectionHeader("3. Switch ON + refused kit_card -> Fallback today's card", scheme: scheme)
                DiscoverRoundupCardView(model: refusedStandardModel, collectionRef: refusedRef)
            }
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)

            let measureHost = hostForMeasurement(columnView, at: .large)
            measureHost.overrideUserInterfaceStyle = uiStyle
            let measured = measureHost.sizeThatFits(in: CGSize(width: 390, height: CGFloat.greatestFiniteMagnitude))
            let height = max(600, ceil(measured.height) + 8)

            let host = hostForMeasurement(columnView, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
            let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: height))
            window.frame = CGRect(x: 0, y: 0, width: 390, height: height)
            window.overrideUserInterfaceStyle = uiStyle
            host.view.frame = window.bounds
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }

            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage), options: [:]).perform([req])
            let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = lines.joined(separator: " ")

            XCTAssertTrue(joined.contains("Kit Card Stand-In Active"), "Expected Kit stand-in card in middle slot (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("42%") && joined.contains("31%") && joined.contains("29%"), "Expected real percents (\(scheme)): \(joined)")
            XCTAssertFalse(joined.contains("0%"), "Must never render 0% (\(scheme)): \(joined)")
            XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero clipped ellipsis (\(scheme)): \(joined)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_KIT_SWITCH_RENDER_DIR"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let tag = scheme == .dark ? "dark" : "light"
                if let png = image.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("kit-switch-366b-\(tag)-390.png"))
                }
            }
        }
        #endif
    }

    private func sectionHeader(_ text: String, scheme: ColorScheme) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(scheme == .dark ? Color.white.opacity(0.75) : Color.black.opacity(0.65))
            .fixedSize(horizontal: false, vertical: true)
    }
}
