import XCTest
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
@testable import Bain_Luck

@MainActor
final class KitV1Renderer366BTests: XCTestCase {

    private func goldenFixtureURL() throws -> URL {
        let testFile = URL(fileURLWithPath: #filePath)
        let url = testFile
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures", isDirectory: true)
            .appendingPathComponent("kit_v1_golden_examples_f066538361.json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path), "Missing fixture at \(url.path)")
        return url
    }

    private func loadGoldenRootObject() throws -> [String: Any] {
        let data = try Data(contentsOf: goldenFixtureURL())
        let raw = try JSONSerialization.jsonObject(with: data)
        return try XCTUnwrap(raw as? [String: Any])
    }

    private func loadGoldenItems() throws -> [[String: Any]] {
        let root = try loadGoldenRootObject()
        let items = try XCTUnwrap(root["items"] as? [[String: Any]])
        XCTAssertEqual(items.count, 8, "Expected 8 worked golden examples in f066538361 fixture")
        return items
    }

    private func collectHTTPSImageURLs(in objects: [[String: Any]]) -> [URL] {
        var found: Set<URL> = []
        func walk(_ node: Any) {
            if let dict = node as? [String: Any] {
                if let urlStr = dict["url"] as? String,
                   KitV1PictureMark.isAllowedHTTPSURL(urlStr),
                   let url = URL(string: urlStr) {
                    found.insert(url)
                }
                if let pic = dict["picture"] as? [String: Any] {
                    walk(pic)
                }
                for value in dict.values {
                    walk(value)
                }
            } else if let arr = node as? [Any] {
                for entry in arr {
                    walk(entry)
                }
            }
        }
        objects.forEach(walk)
        return Array(found)
    }

    private func preloadImages(for urls: [URL]) async -> [URL: PlatformImage] {
        var out: [URL: PlatformImage] = [:]
        await withTaskGroup(of: (URL, PlatformImage?).self) { group in
            for url in urls {
                group.addTask {
                    let config = URLSessionConfiguration.ephemeral
                    config.timeoutIntervalForRequest = 6
                    config.timeoutIntervalForResource = 8
                    let session = URLSession(configuration: config)
                    do {
                        let (data, response) = try await session.data(from: url)
                        guard let http = response as? HTTPURLResponse,
                              (200...299).contains(http.statusCode),
                              let image = PlatformImage(data: data) else {
                            return (url, nil)
                        }
                        return (url, image)
                    } catch {
                        return (url, nil)
                    }
                }
            }
            for await (url, image) in group {
                if let image {
                    out[url] = image
                }
            }
        }
        return out
    }

    private func assertZeroEllipsis(lines: [String], context: String) {
        let bad = lines.filter { $0.contains("…") || $0.contains("...") }
        XCTAssertTrue(bad.isEmpty, "Unexpected truncation/ellipsis in \(context): \(bad)")
    }

    private func assertZeroRawHex(lines: [String], context: String) {
        let regex = try? NSRegularExpression(pattern: "#[0-9a-fA-F]{6}")
        for line in lines {
            let range = NSRange(location: 0, length: (line as NSString).length)
            if regex?.firstMatch(in: line, range: range) != nil {
                XCTFail("Raw hex leaked into rendered text (\(context)): \(line)")
            }
        }
    }

    #if canImport(UIKit)
    private func renderAndRecognize(
        view: some View,
        scheme: ColorScheme,
        dynamicType: DynamicTypeSize = .large
    ) throws -> (UIImage, [String]) {
        let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let bg = scheme == .dark ? Color.black : Color(white: 0.96)
        let framed = view
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, dynamicType)

        let host = hostForMeasurement(framed, at: dynamicType)
        host.overrideUserInterfaceStyle = uiStyle
        let measured = host.sizeThatFits(in: CGSize(width: 390, height: CGFloat.greatestFiniteMagnitude))
        let h = max(120, ceil(measured.height))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: h))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()

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
        return (image, lines)
    }

    private func maybeExportPNG(_ image: UIImage, filename: String) throws {
        guard let outDir = ProcessInfo.processInfo.environment["BUILDER_C_KIT_RENDER_DIR"],
              !outDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        if let png = image.pngData() {
            try png.write(to: dirURL.appendingPathComponent(filename))
        }
    }
    #endif

    // MARK: - 1. Golden Examples Decode + Variant-Agnostic Rule

    func testAllGoldenExamplesDecodeIdenticallyWithRenamedOrMissingVariant() throws {
        let items = try loadGoldenItems()
        for rawItem in items {
            let id = try XCTUnwrap(rawItem["id"] as? String)
            let baselineData = try JSONSerialization.data(withJSONObject: rawItem)
            let baselineSpec = try XCTUnwrap(
                KitV1CardSpec.parse(from: baselineData),
                "Golden example \(id) failed KitV1CardSpec.parse"
            )
            XCTAssertNotNil(
                try? JSONDecoder().decode(KitCardEnvelope366B.self, from: baselineData),
                "Golden example \(id) must also pass KitCardEnvelope366B gate"
            )

            var renamed = rawItem
            renamed["variant"] = "unheard_of_future_bracket_2027"
            let renamedData = try JSONSerialization.data(withJSONObject: renamed)
            let renamedSpec = try XCTUnwrap(KitV1CardSpec.parse(from: renamedData))
            XCTAssertEqual(baselineSpec.layout, renamedSpec.layout, "\(id) layout mismatch on renamed variant")
            XCTAssertEqual(baselineSpec.body, renamedSpec.body, "\(id) body mismatch on renamed variant")

            var missing = rawItem
            missing.removeValue(forKey: "variant")
            let missingData = try JSONSerialization.data(withJSONObject: missing)
            let missingSpec = try XCTUnwrap(KitV1CardSpec.parse(from: missingData))
            XCTAssertEqual(baselineSpec.layout, missingSpec.layout, "\(id) layout mismatch on missing variant")
            XCTAssertEqual(baselineSpec.body, missingSpec.body, "\(id) body mismatch on missing variant")
        }
    }

    // MARK: - 2. Cosmetic vs Meaning-Carrying Field Contract

    func testCosmeticUnknownValuesDrawDefaultAndMeaningUnknownValuesFailClosed() throws {
        let items = try loadGoldenItems()
        let countdownRaw = try XCTUnwrap(items.first(where: { ($0["id"] as? String) == "kit-by-december-31" }))
        let cfbGridRaw = try XCTUnwrap(items.first(where: { ($0["id"] as? String) == "kit-cfb-national-title" }))
        let axisRaw = try XCTUnwrap(items.first(where: { ($0["id"] as? String) == "kit-nhl-playoffs-bubble" }))

        // Cosmetic unknown values MUST still decode & draw default (Fable 11:04 PM / Atlas #13551 agreement).
        var cosmeticCountdown = countdownRaw
        var cosmeticBody = try XCTUnwrap(cosmeticCountdown["body"] as? [String: Any])
        cosmeticBody["header_layout"] = "ticker_future"
        if var headerMarks = cosmeticBody["header_marks"] as? [[String: Any]], !headerMarks.isEmpty {
            headerMarks[0]["prominence"] = "mega"
            headerMarks[0]["tone"] = "ultraviolet"
            headerMarks[0]["align"] = "justify"
            headerMarks[0]["width"] = "xxl"
            cosmeticBody["header_marks"] = headerMarks
        }
        if var rows = cosmeticBody["items"] as? [[String: Any]], !rows.isEmpty,
           var marks = rows[0]["marks"] as? [[String: Any]], !marks.isEmpty {
            marks[0]["size"] = "giant"
            marks[0]["subject_kind"] = "alien_entity"
            marks[1]["style"] = "neon"
            rows[0]["marks"] = marks
            cosmeticBody["items"] = rows
        }
        cosmeticCountdown["body"] = cosmeticBody
        let cosmeticSpec = try XCTUnwrap(
            KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: cosmeticCountdown)),
            "Cosmetic unknown fields must decode cleanly to default instead of falling back"
        )
        XCTAssertNotNil(KitCardView366B(spec: cosmeticSpec), "Cosmetic unknown header_layout/tone/size must still construct KitCardView366B")

        // Meaning-carrying unknown values MUST fail closed (nil -> today's standard card).
        func mutated(_ base: [String: Any], mutate: (inout [String: Any]) -> Void) throws -> Data {
            var copy = base
            mutate(&copy)
            return try JSONSerialization.data(withJSONObject: copy)
        }

        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["kit_version"] = 2 }), "Unknown kit_version must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["layout"] = "radial" }), "Unknown layout must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["refusal_reason"] = "no pictures" }), "Refusal reason must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            b["items"] = []
            $0["body"] = b
        }), "Empty body must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var rows = b["items"] as? [[String: Any]] ?? []
            var marks = rows[0]["marks"] as? [[String: Any]] ?? []
            marks[2]["bar_style"] = "stacked3"
            rows[0]["marks"] = marks
            b["items"] = rows
            $0["body"] = b
        }), "Unknown bar_style must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var rows = b["items"] as? [[String: Any]] ?? []
            var marks = rows[0]["marks"] as? [[String: Any]] ?? []
            marks[2]["fill_color"] = "#008348"
            rows[0]["marks"] = marks
            b["items"] = rows
            $0["body"] = b
        }), "Bare hex string without {light, dark} must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var rows = b["items"] as? [[String: Any]] ?? []
            var marks = rows[0]["marks"] as? [[String: Any]] ?? []
            marks[3]["unit"] = "bps"
            rows[0]["marks"] = marks
            b["items"] = rows
            $0["body"] = b
        }), "Unknown number.unit must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var rows = b["items"] as? [[String: Any]] ?? []
            rows[0]["marks"] = [["mark": "sparkline", "text": "x"]]
            b["items"] = rows
            $0["body"] = b
        }), "Unknown mark must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var rows = b["items"] as? [[String: Any]] ?? []
            var marks = rows[0]["marks"] as? [[String: Any]] ?? []
            marks[0]["url"] = "http://insecure.example.com/logo.png"
            rows[0]["marks"] = marks
            b["items"] = rows
            $0["body"] = b
        }), "Non-HTTPS picture URL must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(cfbGridRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            b["row_layout"] = "masonry"
            $0["body"] = b
        }), "Unknown row_layout must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(axisRaw) {
            var b = $0["body"] as? [String: Any] ?? [:]
            var s = b["scale"] as? [String: Any] ?? [:]
            s["scale_kind"] = "log"
            b["scale"] = s
            $0["body"] = b
        }), "Unknown scale_kind must fail closed")

        // All 3 golden fixture refusals fail closed and standard fallback card renders real rows & percents.
        let root = try loadGoldenRootObject()
        let refusals = try XCTUnwrap(root["refusals"] as? [[String: Any]])
        XCTAssertEqual(refusals.count, 3)
        for refusal in refusals {
            let specObj = try XCTUnwrap(refusal["spec"] as? [String: Any])
            let data = try JSONSerialization.data(withJSONObject: specObj)
            XCTAssertNil(KitV1CardSpec.parse(from: data), "Golden refusal \(refusal["title"] ?? "") must fail closed")
        }

        #if canImport(UIKit)
        let fallbackFeedJSON = #"""
        {
          "type": "bundle",
          "score": 91.0,
          "data": {
            "bundle_id": "bundle-cfb-refusal-fallback",
            "title": "Georgia leads National Title at 34% and SEC Title at 68%",
            "kind": "roundup",
            "collection_ref": {
              "slug": "machinery-cfb-national-title",
              "name": "College Football Playoff",
              "revision": 565166182,
              "collection_count": 6
            },
            "roundup": {
              "kicker": "SPORTS · COLLEGE FOOTBALL",
              "footer": "",
              "rows": [
                {"market_id": 181, "outcome_id": 1, "label": "Georgia · National Title", "probability": 0.34, "rendered_percent": 34},
                {"market_id": 233, "outcome_id": 2, "label": "Texas · SEC Title", "probability": 0.26, "rendered_percent": 26}
              ],
              "machinery_card": {
                "slug": "machinery-cfb-national-title",
                "form_id": "future_unheard_of_look",
                "kicker": "SPORTS · COLLEGE FOOTBALL",
                "title": "Georgia leads National Title at 34% and SEC Title at 68%"
              },
              "kit_card": {
                "kit_version": 1,
                "id": "kit-refused-bar-style",
                "layout": "stack",
                "body": {
                  "items": [
                    {
                      "id": "r1",
                      "marks": [
                        {"mark": "word", "text": "Georgia"},
                        {"mark": "bar", "bar_style": "stacked3", "fill": 0.34, "fill_color": {"light": "#008348", "dark": "#269663"}},
                        {"mark": "number", "value": 34, "display": "34%", "unit": "%"}
                      ]
                    }
                  ]
                }
              }
            },
            "items": []
          }
        }
        """#
        let feedDecoder = JSONDecoder()
        feedDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let feedItem = try feedDecoder.decode(FeedItem.self, from: Data(fallbackFeedJSON.utf8))
        let bundle = try XCTUnwrap(feedItem.bundle)
        let ref = try XCTUnwrap(bundle.roundupCollectionRef)
        let contract = try XCTUnwrap(bundle.roundupContract)
        XCTAssertNil(contract.machineryCard, "Unknown form_id must fail closed")
        XCTAssertNil(contract.kitCard, "Unknown bar_style kit_card must fail closed")
        let fallbackModel = try XCTUnwrap(DiscoverRoundupCardModel.build(
            title: bundle.title,
            contract: contract,
            fallbackKicker: ref.name,
            fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: ref),
            allowFlexibleRowCount: true
        ))
        let (fallbackImg, lines) = try renderAndRecognize(
            view: DiscoverRoundupCardView(model: fallbackModel, collectionRef: ref, onOpenCollection: { _ in }),
            scheme: .light
        )
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("34%") && joined.contains("26%"), "Fallback card must show real percents: \(joined)")
        XCTAssertFalse(joined.contains("0%"), "Fallback card must never show 0%: \(joined)")
        assertZeroEllipsis(lines: lines, context: "refusal fallback")
        try maybeExportPNG(fallbackImg, filename: "kit6b-refusal-fallback-light-390.png")
        #endif
    }

    // MARK: - 3. Milestone 6B Full Render Parity (All 4 Layouts / 8 Examples, Light & Dark, 390pt)

    func testAllEightGoldenExamplesRenderCleanlyLightAndDarkAt390pt() async throws {
        let items = try loadGoldenItems()
        XCTAssertEqual(items.count, 8, "Expected all 8 worked examples (stack, grid, axis, calendar)")

        let urls = collectHTTPSImageURLs(in: items)
        let preloaded = await preloadImages(for: urls)
        XCTAssertFalse(preloaded.isEmpty, "Expected CDN artwork preloaded for Milestone 6B sheets")

        #if canImport(UIKit)
        for rawItem in items {
            let id = try XCTUnwrap(rawItem["id"] as? String)
            let data = try JSONSerialization.data(withJSONObject: rawItem)
            let spec = try XCTUnwrap(KitV1CardSpec.parse(from: data))

            var variantRemoved = rawItem
            variantRemoved.removeValue(forKey: "variant")
            let noVariantSpec = try XCTUnwrap(
                KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: variantRemoved))
            )

            var variantRenamed = rawItem
            variantRenamed["variant"] = "unheard_of_future_bracket_2027"
            let renamedVariantSpec = try XCTUnwrap(
                KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: variantRenamed))
            )

            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let cardView = try XCTUnwrap(KitCardView366B(spec: spec))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (img, lines) = try renderAndRecognize(view: cardView, scheme: scheme)
                let joined = lines.joined(separator: " ")

                XCTAssertTrue(joined.contains("%"), "Expected % on \(id) (\(scheme)); got: \(joined)")
                assertZeroEllipsis(lines: lines, context: "\(id) \(scheme)")
                assertZeroRawHex(lines: lines, context: "\(id) \(scheme)")

                if id == "kit-cfb-national-title" {
                    XCTAssertTrue(joined.contains("Georgia"), "Expected Georgia on grid (\(scheme)); got: \(joined)")
                    XCTAssertTrue(joined.contains("34%"), "Expected 34% on grid (\(scheme)); got: \(joined)")
                    XCTAssertTrue(joined.contains("68%"), "Expected 68% on grid (\(scheme)); got: \(joined)")
                } else if id == "kit-middle-east-deadlines" {
                    XCTAssertTrue(joined.contains("66%") && joined.contains("81%"), "Expected deadline percents on \(id) (\(scheme)); got: \(joined)")
                } else if id == "kit-elon-side-quests" {
                    XCTAssertTrue(joined.contains("1 in 8") || joined.contains("1in8"), "Expected '1 in 8' beside 12% (\(scheme)); got: \(joined)")
                } else if id == "kit-nhl-playoffs-bubble" {
                    XCTAssertTrue(joined.contains("0%") && joined.contains("50%") && joined.contains("100%"), "Expected axis scale ticks on \(id) (\(scheme)); got: \(joined)")
                    XCTAssertTrue(joined.contains("OTT 73%"), "Expected elevated bubble team percents on \(id) (\(scheme)); got: \(joined)")
                    XCTAssertTrue(joined.contains("9 at 25%") && joined.contains("10 at 75%"), "Expected axis summary marks on \(id) (\(scheme)); got: \(joined)")
                } else if id == "kit-spotify-wrapped-2026" {
                    XCTAssertTrue(joined.contains("Nov") && joined.contains("67%") && joined.contains("Dec"), "Expected calendar strip dates and peak percent on \(id) (\(scheme)); got: \(joined)")
                }

                // Variant-agnostic pixel parity across all 8 examples (both missing and renamed variant):
                if scheme == .light {
                    let baselinePNG = img.pngData()
                    let noVariantCard = try XCTUnwrap(KitCardView366B(spec: noVariantSpec))
                        .environment(\.kitPreloadedImages366B, preloaded)
                    let (noVarImg, _) = try renderAndRecognize(view: noVariantCard, scheme: .light)
                    XCTAssertEqual(baselinePNG, noVarImg.pngData(), "Rendered PNG must be identical when variant is removed on \(id)")

                    let renamedVariantCard = try XCTUnwrap(KitCardView366B(spec: renamedVariantSpec))
                        .environment(\.kitPreloadedImages366B, preloaded)
                    let (renVarImg, _) = try renderAndRecognize(view: renamedVariantCard, scheme: .light)
                    XCTAssertEqual(baselinePNG, renVarImg.pngData(), "Rendered PNG must be identical when variant is renamed on \(id)")
                }

                let tag = scheme == .dark ? "dark" : "light"
                try maybeExportPNG(img, filename: "kit6b-\(id)-\(tag)-390.png")
            }

            if id == "kit-by-december-31" {
                let axView = try XCTUnwrap(KitCardView366B(spec: spec))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (axImg, axLines) = try renderAndRecognize(view: axView, scheme: .light, dynamicType: .accessibility5)
                let axJoined = axLines.joined(separator: " ")
                XCTAssertTrue(axJoined.contains("By December"), "AX5 countdown must keep full headline; got: \(axJoined)")
                assertZeroEllipsis(lines: axLines, context: "\(id) AX5")
                try maybeExportPNG(axImg, filename: "kit6b-\(id)-ax5-light-390.png")
            }
        }
        #endif
    }
}
