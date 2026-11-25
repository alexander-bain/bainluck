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
            .appendingPathComponent("kit_v1_golden_examples.json")
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
        XCTAssertFalse(items.isEmpty, "Golden fixture items array must not be empty")
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

    private static var preloadedImageCache: [URL: PlatformImage] = [:]

    private func preloadImages(for urls: [URL]) async -> [URL: PlatformImage] {
        var out: [URL: PlatformImage] = [:]
        var missing: [URL] = []
        for url in urls {
            if let cached = Self.preloadedImageCache[url] {
                out[url] = cached
            } else {
                missing.append(url)
            }
        }
        guard !missing.isEmpty else { return out }

        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 12
        config.timeoutIntervalForResource = 20
        config.httpMaximumConnectionsPerHost = 6
        let session = URLSession(configuration: config)
        defer { session.finishTasksAndInvalidate() }

        await withTaskGroup(of: (URL, PlatformImage?).self) { group in
            for url in missing {
                group.addTask {
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
                    Self.preloadedImageCache[url] = image
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
        width: CGFloat = 390,
        scheme: ColorScheme,
        dynamicType: DynamicTypeSize = .large
    ) async throws -> (UIImage, [String]) {
        let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let bg = scheme == .dark ? Color.black : Color(white: 0.96)
        let framed = view
            .padding(16)
            .frame(width: width, alignment: .topLeading)
            .fixedSize(horizontal: false, vertical: true)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, dynamicType)

        let measureHost = hostForMeasurement(framed, at: dynamicType)
        measureHost.overrideUserInterfaceStyle = uiStyle
        let measured = measureHost.sizeThatFits(in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude))
        let h = max(120, ceil(measured.height) + 4)

        let host = hostForMeasurement(framed, at: dynamicType)
        host.overrideUserInterfaceStyle = uiStyle
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: h))
        window.frame = CGRect(x: 0, y: 0, width: width, height: h)
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

    // MARK: - 1. Table-Driven Golden Examples (Decode + Render + Variant Invariance + Refusals)

    /// Pure data-driven sweep over every item and refusal in `Fixtures/kit_v1_golden_examples.json`.
    /// Adding a new worked example to the JSON file exercises decode, variant invariance, Light/Dark
    /// 390pt rendering, scale ticks/headline/percent OCR, and refusal gating with zero Swift edits.
    func testGoldenExamplesTableDrivenDecodeRenderVariantInvarianceAndOCR() async throws {
        let root = try loadGoldenRootObject()
        let items = try loadGoldenItems()
        let urls = collectHTTPSImageURLs(in: items)
        let preloaded = await preloadImages(for: urls)
        XCTAssertFalse(preloaded.isEmpty, "Expected CDN artwork preloaded for Kit golden examples")

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        var exportedIDs: [String] = []

        for (index, rawItem) in items.enumerated() {
            let id = try XCTUnwrap(rawItem["id"] as? String)
            exportedIDs.append(id)

            let baselineData = try JSONSerialization.data(withJSONObject: rawItem)
            let baselineSpec = try XCTUnwrap(
                KitV1CardSpec.parse(from: baselineData),
                "Golden example \(id) failed KitV1CardSpec.parse"
            )
            XCTAssertNotNil(
                try? decoder.decode(KitCardEnvelope366B.self, from: baselineData),
                "Golden example \(id) must pass KitCardEnvelope366B gate"
            )

            // Defining Kit Test: renaming or removing `variant` cannot alter decoded body or pixels.
            var renamed = rawItem
            renamed["variant"] = "unheard_of_future_bracket_2027"
            let renamedSpec = try XCTUnwrap(KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: renamed)))
            XCTAssertEqual(baselineSpec.layout, renamedSpec.layout, "\(id) layout mismatch when variant renamed")
            XCTAssertEqual(baselineSpec.body, renamedSpec.body, "\(id) body mismatch when variant renamed")

            var missing = rawItem
            missing.removeValue(forKey: "variant")
            let missingSpec = try XCTUnwrap(KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: missing)))
            XCTAssertEqual(baselineSpec.layout, missingSpec.layout, "\(id) layout mismatch when variant removed")
            XCTAssertEqual(baselineSpec.body, missingSpec.body, "\(id) body mismatch when variant removed")

            #if canImport(UIKit)
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let cardView = try XCTUnwrap(KitCardView366B(spec: baselineSpec))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (img, lines) = try await renderAndRecognize(view: cardView, scheme: scheme)
                let joined = lines.joined(separator: " ")

                XCTAssertFalse(lines.isEmpty, "Rendered OCR lines must not be empty for \(id) (\(scheme))")
                XCTAssertTrue(joined.contains("%"), "Expected % value on \(id) (\(scheme)); got: \(joined)")
                assertZeroEllipsis(lines: lines, context: "\(id) \(scheme)")
                assertZeroRawHex(lines: lines, context: "\(id) \(scheme)")

                if let kicker = baselineSpec.kicker, !kicker.isEmpty {
                    let firstToken = kicker.components(separatedBy: .whitespaces).first(where: { $0.count >= 3 })
                    if let firstToken {
                        XCTAssertTrue(
                            joined.localizedCaseInsensitiveContains(firstToken),
                            "Expected kicker token '\(firstToken)' on \(id) (\(scheme)); got: \(joined)"
                        )
                    }
                }

                if case .axis(let axisBody) = baselineSpec.body,
                   let firstTick = axisBody.scale.ticks.first?.label,
                   let lastTick = axisBody.scale.ticks.last?.label {
                    let hasFirstTick = joined.contains(firstTick) || (firstTick == "$0M" && joined.contains("$OM"))
                    XCTAssertTrue(hasFirstTick, "Expected min axis tick '\(firstTick)' on \(id) (\(scheme)); got: \(joined)")
                    XCTAssertTrue(joined.contains(lastTick), "Expected max axis tick '\(lastTick)' on \(id) (\(scheme)); got: \(joined)")
                }

                if scheme == .light {
                    let baselinePNG = img.pngData()
                    let noVariantCard = try XCTUnwrap(KitCardView366B(spec: missingSpec))
                        .environment(\.kitPreloadedImages366B, preloaded)
                    let (noVarImg, _) = try await renderAndRecognize(view: noVariantCard, scheme: .light)
                    XCTAssertEqual(baselinePNG, noVarImg.pngData(), "Rendered PNG changed when variant removed on \(id)")

                    let renamedVariantCard = try XCTUnwrap(KitCardView366B(spec: renamedSpec))
                        .environment(\.kitPreloadedImages366B, preloaded)
                    let (renVarImg, _) = try await renderAndRecognize(view: renamedVariantCard, scheme: .light)
                    XCTAssertEqual(baselinePNG, renVarImg.pngData(), "Rendered PNG changed when variant renamed on \(id)")
                }

                let tag = scheme == .dark ? "dark" : "light"
                let paddedIndex = String(format: "%02d", index + 1)
                try maybeExportPNG(img, filename: "kit6b-\(paddedIndex)-\(id)-\(tag)-390.png")
            }
            #endif
        }

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_KIT_RENDER_DIR"],
           !outDir.isEmpty {
            let manifestURL = URL(fileURLWithPath: outDir, isDirectory: true).appendingPathComponent("manifest.json")
            let manifestData = try JSONSerialization.data(withJSONObject: ["items": exportedIDs])
            try manifestData.write(to: manifestURL)
        }

        // Table-driven check across every refusal in the fixture file.
        let refusals = try XCTUnwrap(root["refusals"] as? [[String: Any]])
        XCTAssertFalse(refusals.isEmpty, "Golden fixture refusals array must not be empty")
        for refusal in refusals {
            let specObj = try XCTUnwrap(refusal["spec"] as? [String: Any])
            let data = try JSONSerialization.data(withJSONObject: specObj)
            XCTAssertNil(KitV1CardSpec.parse(from: data), "Golden refusal \(refusal["title"] ?? "") must fail closed")
            XCTAssertNil(try? decoder.decode(KitCardEnvelope366B.self, from: data), "Envelope gate must reject refusal")
        }
    }

    // MARK: - 2. Unknown Top-Level Key Ignored

    func testUnknownTopLevelKeyIsIgnoredWithoutChangingDecodeOrRender() async throws {
        let items = try loadGoldenItems()
        let firstRaw = try XCTUnwrap(items.first)
        let baselineData = try JSONSerialization.data(withJSONObject: firstRaw)
        let baselineSpec = try XCTUnwrap(KitV1CardSpec.parse(from: baselineData))

        var withUnknownTopLevel = firstRaw
        withUnknownTopLevel["future_telemetry"] = ["experiment": "kit_v2_shadow", "rank_boost": 4.2]
        withUnknownTopLevel["server_debug_token"] = "ok"
        let extendedData = try JSONSerialization.data(withJSONObject: withUnknownTopLevel)

        let extendedSpec = try XCTUnwrap(
            KitV1CardSpec.parse(from: extendedData),
            "Unknown top-level keys must be ignored cleanly, never failing closed"
        )
        XCTAssertEqual(extendedSpec, baselineSpec, "Unknown top-level keys must decode to the exact same KitV1CardSpec")

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertNotNil(
            try? decoder.decode(KitCardEnvelope366B.self, from: extendedData),
            "Envelope gate must also ignore unknown top-level keys"
        )

        #if canImport(UIKit)
        let preloaded = await preloadImages(for: collectHTTPSImageURLs(in: [firstRaw]))
        let baseCard = try XCTUnwrap(KitCardView366B(spec: baselineSpec))
            .environment(\.kitPreloadedImages366B, preloaded)
        let extCard = try XCTUnwrap(KitCardView366B(spec: extendedSpec))
            .environment(\.kitPreloadedImages366B, preloaded)
        let (baseImg, _) = try await renderAndRecognize(view: baseCard, scheme: .light)
        let (extImg, _) = try await renderAndRecognize(view: extCard, scheme: .light)
        XCTAssertEqual(baseImg.pngData(), extImg.pngData(), "Unknown top-level key must render identically")
        #endif
    }

    // MARK: - 3. Countdown Computed On-Device From `deadline_iso`

    func testCountdownDeadlineIsoUpdatesNumberAndHeroLabelFromPhoneClock() async throws {
        // Deadline is 2026-12-31T23:59:00 PT (`America/Los_Angeles`).
        let deadlineISO = "2026-12-31T23:59:00-08:00"
        let rawCountdown: [String: Any] = [
            "kit_version": 1,
            "id": "kit-countdown-deadline-test",
            "layout": "stack",
            "variant": "countdown",
            "kicker": "TECH & CULTURE",
            "common_headline": "By December 31: deadline countdown",
            "stat_caption": "Claude leads Dec 31 deadlines at 85%.",
            "body": [
                "header_layout": "banner",
                "header_marks": [
                    [
                        "mark": "number",
                        "value": 38,
                        "display": "38",
                        "unit": "days",
                        "deadline_iso": deadlineISO,
                        "tone": "accent",
                        "prominence": "hero",
                        "align": "left",
                        "width": "auto",
                    ],
                    [
                        "mark": "word",
                        "text": "days left",
                        "style": "hero_label",
                        "tone": "primary",
                        "align": "left",
                        "width": "flex",
                        "bold": true,
                        "secondary_text": "all of these end on Dec 31",
                    ],
                ],
                "items": [
                    [
                        "id": "cd-opus",
                        "marks": [
                            ["mark": "word", "text": "Next Claude Opus", "style": "row", "tone": "primary", "width": "flex"],
                            ["mark": "bar", "bar_style": "single", "fill": 0.85, "width": "sm"],
                            ["mark": "number", "value": 85, "display": "85%", "unit": "%", "width": "sm"],
                        ],
                    ],
                ],
            ],
        ]

        let spec = try XCTUnwrap(KitV1CardSpec.parse(from: JSONSerialization.data(withJSONObject: rawCountdown)))

        let formatter = ISO8601DateFormatter()
        let fourDaysBefore = try XCTUnwrap(formatter.date(from: "2026-12-27T10:00:00-08:00"))
        let oneDayBefore = try XCTUnwrap(formatter.date(from: "2026-12-30T14:00:00-08:00"))
        let sameDayPT = try XCTUnwrap(formatter.date(from: "2026-12-31T08:00:00-08:00"))
        let pastDeadlinePT = try XCTUnwrap(formatter.date(from: "2027-01-01T09:00:00-08:00"))

        XCTAssertEqual(KitCountdownClock366B.daysLeft(from: deadlineISO, now: fourDaysBefore), 4)
        XCTAssertEqual(KitCountdownClock366B.daysLeft(from: deadlineISO, now: oneDayBefore), 1)
        XCTAssertEqual(KitCountdownClock366B.daysLeft(from: deadlineISO, now: sameDayPT), 0)
        XCTAssertEqual(KitCountdownClock366B.daysLeft(from: deadlineISO, now: pastDeadlinePT), -1)

        // Malformed deadline_iso fails closed rather than rendering wrong countdown.
        var badDeadline = rawCountdown
        if var b = badDeadline["body"] as? [String: Any],
           var hdr = b["header_marks"] as? [[String: Any]] {
            hdr[0]["deadline_iso"] = "not-a-date"
            b["header_marks"] = hdr
            badDeadline["body"] = b
        }
        XCTAssertNil(KitV1CardSpec.parse(from: try JSONSerialization.data(withJSONObject: badDeadline)))

        #if canImport(UIKit)
        let oneDayCard = try XCTUnwrap(KitCardView366B(spec: spec, now: oneDayBefore))
        let (_, oneDayLines) = try await renderAndRecognize(view: oneDayCard, scheme: .light)
        let oneDayJoined = oneDayLines.joined(separator: " ")
        XCTAssertTrue(oneDayJoined.contains("1") && oneDayJoined.contains("day left"), "Expected '1 day left'; got: \(oneDayJoined)")
        XCTAssertFalse(oneDayJoined.contains("38"), "Phone clock must supersede stale cached '38' display: \(oneDayJoined)")

        let sameDayCard = try XCTUnwrap(KitCardView366B(spec: spec, now: sameDayPT))
        let (_, sameDayLines) = try await renderAndRecognize(view: sameDayCard, scheme: .light)
        let sameDayJoined = sameDayLines.joined(separator: " ")
        XCTAssertTrue(sameDayJoined.contains("Today") && sameDayJoined.contains("ends today"), "Expected 'Today ends today'; got: \(sameDayJoined)")

        let pastCard = try XCTUnwrap(KitCardView366B(spec: spec, now: pastDeadlinePT))
        let (_, pastLines) = try await renderAndRecognize(view: pastCard, scheme: .light)
        let pastJoined = pastLines.joined(separator: " ")
        XCTAssertTrue(pastJoined.contains("Today") && pastJoined.contains("ends today"), "Past deadline stays 'Today ends today'; got: \(pastJoined)")
        #endif
    }

    // MARK: - 4. Picture Shape Rule & Equal Crest Boxes

    func testPictureShapeRuleAndUniformCrestBoxesAcrossRowsAndAxis() {
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "person"), .roundPerson)
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "team"), .containedCrest)
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "organization"), .containedCrest)
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "flag"), .containedCrest)
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "film"), .uprightPoster)
        XCTAssertEqual(KitPictureShape366B.resolve(forSubjectKind: "topic"), .roundedTopic)

        // Crests (`team`, `organization`, `flag`) have the exact same `24×24` box across `.xs` and `.sm` rows.
        let teamXs = KitPictureMarkView366B(mark: KitV1PictureMark(url: "https://example.com/a.png", alt: "NYR", subjectKind: "team", size: .xs, contain: true))
        let teamSm = KitPictureMarkView366B(mark: KitV1PictureMark(url: "https://example.com/b.png", alt: "CAR", subjectKind: "team", size: .sm, contain: true))
        let orgXs = KitPictureMarkView366B(mark: KitV1PictureMark(url: "https://example.com/c.png", alt: "Claude", subjectKind: "organization", size: .xs, contain: true))
        let flagSm = KitPictureMarkView366B(mark: KitV1PictureMark(url: "https://example.com/d.png", alt: "US", subjectKind: "flag", size: .sm, contain: true))
        XCTAssertEqual(teamXs.renderedBoxSize, CGSize(width: 24, height: 24))
        XCTAssertEqual(teamSm.renderedBoxSize, CGSize(width: 24, height: 24))
        XCTAssertEqual(orgXs.renderedBoxSize, CGSize(width: 24, height: 24))
        XCTAssertEqual(flagSm.renderedBoxSize, CGSize(width: 24, height: 24))

        // Upright `2:3` poster for film, regardless of `contain`.
        let poster = KitPictureMarkView366B(mark: KitV1PictureMark(url: "https://example.com/poster.jpg", alt: "The Odyssey", subjectKind: "film", size: .sm, contain: true))
        XCTAssertEqual(poster.renderedBoxSize, CGSize(width: 20, height: 30))

        // Axis dots with fixedSquareBox enforce identical `24×24` boxes for Capitals / Rangers / Islanders.
        let axisCap = KitPictureMarkView366B(
            mark: KitV1PictureMark(url: "https://example.com/wsh.png", alt: "WSH", subjectKind: "team", size: .xs, contain: true),
            fixedSquareBox: 24
        )
        let axisNyr = KitPictureMarkView366B(
            mark: KitV1PictureMark(url: "https://example.com/nyr.png", alt: "NYR", subjectKind: "team", size: .sm, contain: true),
            fixedSquareBox: 24
        )
        XCTAssertEqual(axisCap.renderedBoxSize, axisNyr.renderedBoxSize)
    }

    // MARK: - 5. Cosmetic vs Meaning-Carrying Contract Table

    func testCosmeticUnknownValuesDrawDefaultAndMeaningUnknownValuesFailClosed() async throws {
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
        XCTAssertNotNil(KitCardView366B(spec: cosmeticSpec))

        // Meaning-carrying unknown values MUST fail closed (`nil` -> today's standard card).
        func mutated(_ base: [String: Any], mutate: (inout [String: Any]) -> Void) throws -> Data {
            var copy = base
            mutate(&copy)
            return try JSONSerialization.data(withJSONObject: copy)
        }

        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["kit_version"] = 2 }), "Unknown kit_version must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["layout"] = "radial" }), "Unknown layout must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["refusal_reason"] = "no pictures" }), "Refusal reason must fail closed")
        XCTAssertNil(KitV1CardSpec.parse(from: try mutated(countdownRaw) { $0["fallback_today"] = true }), "fallback_today=true must fail closed")
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
        XCTAssertNil(contract.machineryCard)
        XCTAssertNil(contract.kitCard)
        let fallbackModel = try XCTUnwrap(DiscoverRoundupCardModel.build(
            title: bundle.title,
            contract: contract,
            fallbackKicker: ref.name,
            fallbackFooter: DiscoverRoundupCardModel.fallbackFooter(for: ref),
            allowFlexibleRowCount: true
        ))
        let (fallbackImg, lines) = try await renderAndRecognize(
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

    // MARK: - 6. AX5 (390pt) & iPad Two-Column (768pt) Sheet Verification

    func testAX5AndIPadTwoColumnLayoutsRenderWithZeroTruncation() async throws {
        let items = try loadGoldenItems()
        let urls = collectHTTPSImageURLs(in: items)
        let preloaded = await preloadImages(for: urls)

        let specs = try items.map { raw in
            try XCTUnwrap(KitV1CardSpec.parse(from: try JSONSerialization.data(withJSONObject: raw)))
        }
        // Select representative cards from all 4 layouts (including multi-column grid where AX5 breaks first).
        let axIds = [
            "kit-cfb-national-title",
            "kit-batch1-nba-awards",
            "kit-middle-east-deadlines",
            "kit-by-december-31",
            "kit-nhl-playoffs-bubble",
            "kit-spotify-wrapped-2026",
            "kit-batch1-box-office-scale",
            "kit-elon-side-quests",
        ]
        let axSpecs = axIds.compactMap { id in specs.first(where: { $0.id == id }) }
        XCTAssertGreaterThanOrEqual(axSpecs.count, 6)

        #if canImport(UIKit)
        for spec in axSpecs {
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let card = try XCTUnwrap(KitCardView366B(spec: spec))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (axImg, axLines) = try await renderAndRecognize(
                    view: card,
                    width: 390,
                    scheme: scheme,
                    dynamicType: .accessibility5
                )
                XCTAssertLessThanOrEqual(axImg.size.width, 391, "AX5 render exceeded 390pt width on \(spec.id) (\(scheme))")
                let joined = axLines.joined(separator: " ")
                XCTAssertTrue(joined.contains("%"), "AX5 render lost percent on \(spec.id) (\(scheme)): \(joined)")
                if spec.id == "kit-batch1-box-office-scale" {
                    XCTAssertTrue(joined.contains("Opening weekend"), "AX5 render clipped headline on \(spec.id) (\(scheme)): \(joined)")
                    XCTAssertTrue(joined.contains("$460M"), "AX5 render clipped axis endpoint '$460M' on \(spec.id) (\(scheme)): \(joined)")
                }
                assertZeroEllipsis(lines: axLines, context: "\(spec.id) AX5 \(scheme)")
                assertZeroRawHex(lines: axLines, context: "\(spec.id) AX5 \(scheme)")
                let tag = scheme == .dark ? "dark" : "light"
                try maybeExportPNG(axImg, filename: "kit6b-ax5-\(spec.id)-\(tag)-390.png")
            }
        }

        // iPad 2-column layout (768pt portrait width, two ~356pt columns matching Discover / Set Pages).
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let twoColView = VStack(alignment: .leading, spacing: 14) {
                ForEach(stride(from: 0, to: axSpecs.count, by: 2).map { $0 }, id: \.self) { rowIdx in
                    HStack(alignment: .top, spacing: 16) {
                        if let left = KitCardView366B(spec: axSpecs[rowIdx]) {
                            left.environment(\.kitPreloadedImages366B, preloaded)
                                .frame(maxWidth: .infinity, alignment: .topLeading)
                        }
                        if rowIdx + 1 < axSpecs.count,
                           let right = KitCardView366B(spec: axSpecs[rowIdx + 1]) {
                            right.environment(\.kitPreloadedImages366B, preloaded)
                                .frame(maxWidth: .infinity, alignment: .topLeading)
                        } else {
                            Color.clear.frame(maxWidth: .infinity)
                        }
                    }
                }
            }
            let (ipadImg, ipadLines) = try await renderAndRecognize(
                view: twoColView,
                width: 768,
                scheme: scheme,
                dynamicType: .large
            )
            let ipadJoined = ipadLines.joined(separator: " ")
            XCTAssertTrue(ipadJoined.contains("%"), "iPad 2-col render missing percentages (\(scheme))")
            assertZeroEllipsis(lines: ipadLines, context: "iPad 2-col \(scheme)")
            assertZeroRawHex(lines: ipadLines, context: "iPad 2-col \(scheme)")
            let tag = scheme == .dark ? "dark" : "light"
            try maybeExportPNG(ipadImg, filename: "kit6b-ipad-twocol-\(tag)-768.png")
        }
        #endif
    }
}
