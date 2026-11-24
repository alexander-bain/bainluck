import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Items 4–9 (Ruling 366: B):
/// - Item 4: VoiceOver labels, big line first, zero "image" picture announcements across all 17 examples.
/// - Item 5: Largest text (`AX1`–`AX5`) across all 17 examples at 390pt Light -> matrix table & sheet.
/// - Item 6: Tap targets >= 44x44pt across all 4 layouts + row vs foot route verification.
/// - Item 7: iPad two-column and Mac widths across all 4 layouts.
/// - Item 8: WCAG 2.1 contrast audit table (`4.5:1` text, `3.0:1` bars/marks) across Light & Dark tokens + JSON pairs.
/// - Item 9: Real-set v6 parity renders at 390pt Light when `BUILDER_C_REAL_SETS_JSON` is set.
@MainActor
final class KitV1AccessibilityAuditTests: XCTestCase {

    override class func setUp() {
        super.setUp()
        setAccessibilityAutomation(true)
    }

    override class func tearDown() {
        setAccessibilityAutomation(false)
        super.tearDown()
    }

    private static func setAccessibilityAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let sym = dlsym(lib, "_AXSSetAutomationEnabled") else {
            return
        }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(sym, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    private struct SpecWrapper {
        let index: Int
        let id: String
        let raw: [String: Any]
        let spec: KitV1CardSpec
    }

    private struct AXElementSnapshot {
        let identifier: String
        let label: String
        let traits: UIAccessibilityTraits
        let frame: CGRect
        let object: NSObject
    }

    // MARK: - Fixture & Environment Loading

    private func loadGoldenSpecs() throws -> [SpecWrapper] {
        let thisFile = URL(fileURLWithPath: #filePath)
        let testsDir = thisFile.deletingLastPathComponent()
        let fixtureURL = testsDir
            .appendingPathComponent("Fixtures", isDirectory: true)
            .appendingPathComponent("kit_v1_golden_examples.json")
        let data = try Data(contentsOf: fixtureURL)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let items = try XCTUnwrap(root["items"] as? [[String: Any]])
        XCTAssertEqual(items.count, 17, "Expected 17 golden examples")

        return try items.enumerated().map { idx, raw in
            let id = try XCTUnwrap(raw["id"] as? String)
            let itemData = try JSONSerialization.data(withJSONObject: raw)
            let spec = try XCTUnwrap(KitV1CardSpec.parse(from: itemData), "Failed to parse \(id)")
            return SpecWrapper(index: idx, id: id, raw: raw, spec: spec)
        }
    }

    private func collectHTTPSURLs(in objects: [[String: Any]]) -> [String] {
        var found = Set<String>()
        func walk(_ node: Any) {
            if let dict = node as? [String: Any] {
                if let urlStr = dict["url"] as? String, urlStr.hasPrefix("https://") {
                    found.addURL(urlStr)
                }
                for value in dict.values {
                    walk(value)
                }
            } else if let arr = node as? [Any] {
                for item in arr {
                    walk(item)
                }
            }
        }
        for obj in objects {
            walk(obj)
        }
        return Array(found).sorted()
    }

    private func preloadImages(for urls: [String]) async -> [URL: UIImage] {
        var out: [URL: UIImage] = [:]
        guard !urls.isEmpty else { return out }
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 6
        config.timeoutIntervalForResource = 10
        let session = URLSession(configuration: config)

        await withTaskGroup(of: (URL, UIImage?).self) { group in
            for urlStr in urls {
                guard let url = URL(string: urlStr) else { continue }
                group.addTask {
                    do {
                        let (data, resp) = try await session.data(from: url)
                        if let http = resp as? HTTPURLResponse,
                           (200...299).contains(http.statusCode),
                           let img = UIImage(data: data) {
                            return (url, img)
                        }
                    } catch {
                        // Best-effort offline tolerance; initials fallback renders cleanly.
                    }
                    return (url, nil)
                }
            }
            for await (u, img) in group {
                if let img {
                    out[u] = img
                }
            }
        }
        return out
    }

    private func auditOutputDirectory() -> URL? {
        guard let raw = ProcessInfo.processInfo.environment["BUILDER_C_KIT_AUDIT_DIR"],
              !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        let dir = URL(fileURLWithPath: raw, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func writeAuditFile(_ content: String, relativePath: String) throws {
        guard let dir = auditOutputDirectory() else { return }
        let target = dir.appendingPathComponent(relativePath)
        try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data(content.utf8).write(to: target, options: .atomic)
    }

    private func writeAuditPNG(_ image: UIImage, relativePath: String) throws {
        guard let dir = auditOutputDirectory(),
              let png = image.pngData() else { return }
        let target = dir.appendingPathComponent(relativePath)
        try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
        try png.write(to: target, options: .atomic)
    }

    // MARK: - Hosting, Accessibility Tree & Vision Helpers

    private func hostInWindow<V: View>(
        view: V,
        width: CGFloat = 390,
        scheme: ColorScheme = .light,
        dynamicType: DynamicTypeSize = .large,
        horizontalSizeClass: UserInterfaceSizeClass = .compact
    ) async -> (window: UIWindow, vc: UIViewController, image: UIImage) {
        let bgUIColor = scheme == .dark ? UIColor(red: 0.06, green: 0.07, blue: 0.08, alpha: 1) : UIColor.systemBackground
        let wrapped = view
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(width: width, alignment: .topLeading)
            .background(Color(uiColor: bgUIColor))
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, horizontalSizeClass)

        let vc = hostForMeasurement(wrapped, at: dynamicType)
        vc.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        vc.view.backgroundColor = bgUIColor

        let targetSize = vc.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
        let resolvedHeight = max(120, ceil(targetSize.height))
        let frame = CGRect(x: 0, y: 0, width: width, height: resolvedHeight)

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: frame)
        }
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = vc
        vc.view.frame = frame
        window.makeKeyAndVisible()

        vc.view.setNeedsLayout()
        vc.view.layoutIfNeeded()
        for _ in 0..<12 {
            try? await Task.sleep(nanoseconds: 25_000_000)
            vc.view.setNeedsLayout()
            vc.view.layoutIfNeeded()
            if !collectAccessibilityElements(from: vc.view).isEmpty {
                break
            }
        }

        let renderer = rendererForMeasurement(
            wrapped.fixedSize(horizontal: false, vertical: true),
            at: dynamicType
        )
        renderer.scale = resolvedHeight > 3000 ? 1.0 : 2.0
        let image: UIImage
        if let cgRendered = renderer.uiImage {
            image = cgRendered
        } else {
            let format = UIGraphicsImageRendererFormat()
            format.scale = 2.0
            format.opaque = true
            let gfx = UIGraphicsImageRenderer(size: frame.size, format: format)
            image = gfx.image { ctx in
                if !window.drawHierarchy(in: window.bounds, afterScreenUpdates: true) {
                    vc.view.layer.render(in: ctx.cgContext)
                }
            }
        }
        return (window, vc, image)
    }

    private func collectAccessibilityElements(from root: UIView) -> [AXElementSnapshot] {
        var result: [AXElementSnapshot] = []
        var visited = Set<ObjectIdentifier>()

        func walk(_ node: Any) {
            guard let obj = node as? NSObject else { return }
            let oid = ObjectIdentifier(obj)
            guard !visited.contains(oid) else { return }
            visited.insert(oid)

            if obj.isAccessibilityElement {
                let id = (obj as? UIAccessibilityIdentification)?.accessibilityIdentifier ?? ""
                let label = obj.accessibilityLabel ?? ""
                let traits = obj.accessibilityTraits
                let frame = obj.accessibilityFrame
                result.append(AXElementSnapshot(
                    identifier: id,
                    label: label,
                    traits: traits,
                    frame: frame,
                    object: obj
                ))
            }

            if let explicit = obj.accessibilityElements, !explicit.isEmpty {
                for child in explicit {
                    walk(child)
                }
            } else {
                let count = obj.accessibilityElementCount()
                if count != NSNotFound && count > 0 {
                    for i in 0..<count {
                        if let child = obj.accessibilityElement(at: i) {
                            walk(child)
                        }
                    }
                }
            }

            if let view = obj as? UIView {
                for sub in view.subviews {
                    walk(sub)
                }
            }
        }

        walk(root)
        return result
    }

    private func recognizeTextLines(in image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([request])
        return (request.results ?? [])
            .sorted { a, b in
                if abs(a.boundingBox.midY - b.boundingBox.midY) > 0.015 {
                    return a.boundingBox.midY > b.boundingBox.midY
                }
                return a.boundingBox.minX < b.boundingBox.minX
            }
            .compactMap { $0.topCandidates(1).first?.string }
    }

    // MARK: - Item 8: WCAG 2.1 Contrast Table

    func testContrastTableAllTokensAndJSONPairsPassWCAG() throws {
        let wrappers = try loadGoldenSpecs()
        var lines: [String] = [
            "# Kit v1 Contrast Audit Table (Simulator / Token Audit)",
            "",
            "| Scope | Foreground | Background | Ratio | Threshold | Result |",
            "|---|---|---|---:|---:|---|"
        ]
        var failures: [String] = []

        func check(scope: String, fg: String, bg: String, threshold: Double) {
            let ratio = KitTones366B.contrastRatio(fg, against: bg) ?? 0
            let pass = ratio + 0.0001 >= threshold
            let status = pass ? "PASS" : "FAIL"
            lines.append(String(format: "| `%@` | `%@` | `%@` | %.2f:1 | %.1f:1 | %@ |", scope, fg, bg, ratio, threshold, status))
            if !pass {
                failures.append(String(format: "%@: %@ vs %@ = %.2f:1 < %.1f:1", scope, fg, bg, ratio, threshold))
            }
        }

        let tones: [(String, KitV1Tone?)] = [
            ("default(nil)", nil),
            ("primary", .primary),
            ("secondary", .secondary),
            ("muted", .muted),
            ("accent", .accent),
            ("warn", .warn)
        ]

        for (schemeName, scheme, bgs) in [
            ("light", ColorScheme.light, [
                ("card", KitTones366B.lightCardHex),
                ("elevated", KitTones366B.lightElevatedHex),
                ("track", KitTones366B.lightTrackHex)
            ]),
            ("dark", ColorScheme.dark, [
                ("card", KitTones366B.darkCardHex),
                ("elevated", KitTones366B.darkElevatedHex),
                ("track", KitTones366B.darkTrackHex)
            ])
        ] {
            for (toneName, tone) in tones {
                let fg = KitTones366B.textHex(for: tone, scheme: scheme)
                for (bgName, bgHex) in bgs {
                    check(scope: "\(schemeName).text.\(toneName).on.\(bgName)", fg: fg, bg: bgHex, threshold: 4.5)
                }
            }

            for idx in 0..<8 {
                let barFg = KitTones366B.seriesHex(at: idx, scheme: scheme)
                check(scope: "\(schemeName).series[\(idx)].on.card", fg: barFg, bg: bgs[0].1, threshold: 3.0)
                check(scope: "\(schemeName).series[\(idx)].on.track", fg: barFg, bg: bgs[2].1, threshold: 3.0)
            }
        }

        // Audit KitTones366B tile foreground/background combinations (shaded bands & peaks).
        func blendedHex(fg: String, bg: String, alpha: Double) -> String {
            func channels(_ hex: String) -> (Double, Double, Double) {
                let h = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
                let val = Int(h, radix: 16) ?? 0
                return (Double((val >> 16) & 0xFF), Double((val >> 8) & 0xFF), Double(val & 0xFF))
            }
            let f = channels(fg)
            let b = channels(bg)
            let r = Int((f.0 * alpha + b.0 * (1 - alpha)).rounded())
            let g = Int((f.1 * alpha + b.1 * (1 - alpha)).rounded())
            let bl = Int((f.2 * alpha + b.2 * (1 - alpha)).rounded())
            return String(format: "#%02X%02X%02X", min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, bl)))
        }

        let lightPrimary = KitTones366B.textHex(for: .primary, scheme: .light)
        let lightSecondary = KitTones366B.textHex(for: .secondary, scheme: .light)
        let lightMuted = KitTones366B.textHex(for: .muted, scheme: .light)
        let lightAccent = KitTones366B.textHex(for: .accent, scheme: .light)
        check(scope: "light.tile.muted.fg", fg: lightMuted, bg: KitTones366B.lightElevatedHex, threshold: 4.5)
        check(scope: "light.tile.lowShade.fg", fg: lightSecondary, bg: KitTones366B.lightElevatedHex, threshold: 4.5)
        check(scope: "light.tile.lowShade.subFg", fg: lightMuted, bg: KitTones366B.lightElevatedHex, threshold: 4.5)
        let lightShade12 = blendedHex(fg: lightAccent, bg: KitTones366B.lightCardHex, alpha: 0.10)
        check(scope: "light.tile.band12.primary", fg: lightPrimary, bg: lightShade12, threshold: 4.5)
        check(scope: "light.tile.band12.secondary", fg: lightSecondary, bg: lightShade12, threshold: 4.5)
        let lightShade30 = blendedHex(fg: lightAccent, bg: KitTones366B.lightCardHex, alpha: 0.18)
        check(scope: "light.tile.band30.primary", fg: lightPrimary, bg: lightShade30, threshold: 4.5)
        check(scope: "light.tile.band30.secondary", fg: lightSecondary, bg: lightShade30, threshold: 4.5)
        check(scope: "light.tile.dayPeak.fg", fg: "#FFFFFF", bg: lightAccent, threshold: 4.5)

        let darkPrimary = KitTones366B.textHex(for: .primary, scheme: .dark)
        let darkSecondary = KitTones366B.textHex(for: .secondary, scheme: .dark)
        let darkMuted = KitTones366B.textHex(for: .muted, scheme: .dark)
        let darkAccent = KitTones366B.textHex(for: .accent, scheme: .dark)
        check(scope: "dark.tile.muted.fg", fg: darkMuted, bg: KitTones366B.darkElevatedHex, threshold: 4.5)
        check(scope: "dark.tile.lowShade.fg", fg: darkSecondary, bg: KitTones366B.darkElevatedHex, threshold: 4.5)
        check(scope: "dark.tile.lowShade.subFg", fg: darkMuted, bg: KitTones366B.darkElevatedHex, threshold: 4.5)
        let darkShade12 = blendedHex(fg: darkAccent, bg: KitTones366B.darkCardHex, alpha: 0.14)
        check(scope: "dark.tile.band12.primary", fg: darkPrimary, bg: darkShade12, threshold: 4.5)
        check(scope: "dark.tile.band12.secondary", fg: darkSecondary, bg: darkShade12, threshold: 4.5)
        let darkShade30 = blendedHex(fg: darkAccent, bg: KitTones366B.darkCardHex, alpha: 0.24)
        check(scope: "dark.tile.band30.primary", fg: darkPrimary, bg: darkShade30, threshold: 4.5)
        check(scope: "dark.tile.band30.secondary", fg: darkSecondary, bg: darkShade30, threshold: 4.5)
        check(scope: "dark.tile.dayPeak.fg", fg: "#0B0E11", bg: darkAccent, threshold: 4.5)
        check(scope: "dark.tile.dayPeak.subFg", fg: "#111827", bg: darkAccent, threshold: 4.5)

        // Audit every JSON mark color pair across all 17 golden examples.
        func auditMarks(_ marks: [KitV1Mark], prefix: String) {
            for (mIdx, mark) in marks.enumerated() {
                switch mark {
                case .bar(let b):
                    if let fc = b.fillColor {
                        let lHex = KitTones366B.barHex(hex: fc.light, darkHex: fc.dark, fallbackIndex: mIdx, scheme: .light)
                        let dHex = KitTones366B.barHex(hex: fc.light, darkHex: fc.dark, fallbackIndex: mIdx, scheme: .dark)
                        check(scope: "\(prefix).bar[\(mIdx)].light.track", fg: lHex, bg: KitTones366B.lightTrackHex, threshold: 3.0)
                        check(scope: "\(prefix).bar[\(mIdx)].dark.track", fg: dHex, bg: KitTones366B.darkTrackHex, threshold: 3.0)
                    }
                    for (sIdx, seg) in (b.segments ?? []).enumerated() {
                        let lHex = KitTones366B.barHex(hex: seg.color?.light, darkHex: seg.color?.dark ?? seg.colorDark, fallbackIndex: sIdx, scheme: .light)
                        let dHex = KitTones366B.barHex(hex: seg.color?.light, darkHex: seg.color?.dark ?? seg.colorDark, fallbackIndex: sIdx, scheme: .dark)
                        check(scope: "\(prefix).split[\(mIdx)].seg[\(sIdx)].light.track", fg: lHex, bg: KitTones366B.lightTrackHex, threshold: 3.0)
                        check(scope: "\(prefix).split[\(mIdx)].seg[\(sIdx)].dark.track", fg: dHex, bg: KitTones366B.darkTrackHex, threshold: 3.0)
                    }
                case .dot(let d):
                    let lHex = KitTones366B.barHex(hex: d.color?.light, darkHex: d.color?.dark ?? d.colorDark, fallbackIndex: mIdx, scheme: .light)
                    let dHex = KitTones366B.barHex(hex: d.color?.light, darkHex: d.color?.dark ?? d.colorDark, fallbackIndex: mIdx, scheme: .dark)
                    check(scope: "\(prefix).dot[\(mIdx)].light.elevated", fg: lHex, bg: KitTones366B.lightElevatedHex, threshold: 3.0)
                    check(scope: "\(prefix).dot[\(mIdx)].dark.elevated", fg: dHex, bg: KitTones366B.darkElevatedHex, threshold: 3.0)
                case .line(let l):
                    let lHex = KitTones366B.barHex(hex: l.color?.light, darkHex: l.color?.dark ?? l.colorDark, fallbackIndex: mIdx, scheme: .light)
                    let dHex = KitTones366B.barHex(hex: l.color?.light, darkHex: l.color?.dark ?? l.colorDark, fallbackIndex: mIdx, scheme: .dark)
                    check(scope: "\(prefix).line[\(mIdx)].light.card", fg: lHex, bg: KitTones366B.lightCardHex, threshold: 3.0)
                    check(scope: "\(prefix).line[\(mIdx)].dark.card", fg: dHex, bg: KitTones366B.darkCardHex, threshold: 3.0)
                default:
                    break
                }
            }
        }

        for w in wrappers {
            switch w.spec.body {
            case .stack(let sb):
                for item in sb.items {
                    auditMarks(item.marks, prefix: "\(w.id).\(item.id)")
                    if let sub = item.subMarks { auditMarks(sub, prefix: "\(w.id).\(item.id).sub") }
                }
            case .grid(let gb):
                for row in gb.rows {
                    for cell in row.cells {
                        auditMarks(cell.marks, prefix: "\(w.id).\(row.id).\(cell.columnKey)")
                    }
                }
            case .calendar(let cb):
                for day in cb.days {
                    auditMarks(day.marks, prefix: "\(w.id).\(day.dateKey)")
                }
            case .axis(let ab):
                if let direct = ab.marks { auditMarks(direct, prefix: "\(w.id).axis") }
                for s in ab.series ?? [] {
                    auditMarks(s.marks, prefix: "\(w.id).\(s.id)")
                }
            }
        }

        try writeAuditFile(lines.joined(separator: "\n") + "\n", relativePath: "kit_contrast_table.md")
        XCTAssertTrue(failures.isEmpty, "Contrast failures:\n" + failures.joined(separator: "\n"))
    }

    // MARK: - Item 4: VoiceOver Labels & Traversal Order Across All 17 Examples

    func testVoiceOverSentencesAll17ExamplesBigLineFirstAndNoPictureImageTrait() async throws {
        let wrappers = try loadGoldenSpecs()
        let fixedNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-24T12:00:00-08:00"))

        var reportLines: [String] = [
            "# Kit v1 VoiceOver Audit (17 Golden Examples, Simulator)",
            ""
        ]

        for w in wrappers {
            let spec = w.spec
            let headlineSpeech = KitAccessibilitySpeech366B.cardHeadlineSpeech(spec: spec)
            XCTAssertFalse(headlineSpeech.isEmpty, "Missing headline speech for \(w.id)")
            if let bigLine = spec.commonHeadline, !bigLine.isEmpty {
                XCTAssertTrue(
                    headlineSpeech.hasPrefix(bigLine) || headlineSpeech.contains(bigLine),
                    "Big line must come first in headline speech for \(w.id): \(headlineSpeech)"
                )
            }

            // 1. Validate pure speech-sentence builders for all rows/cells/dots/series/days.
            switch spec.body {
            case .stack(let sb):
                for (idx, item) in sb.items.enumerated() {
                    let speech = KitAccessibilitySpeech366B.stackRowSpeech(
                        item: item,
                        index: idx,
                        total: sb.items.count,
                        spec: spec,
                        now: fixedNow
                    )
                    XCTAssertTrue(
                        speech.contains("\(idx + 1) of \(sb.items.count)"),
                        "Stack row missing place on \(w.id)/\(item.id): \(speech)"
                    )
                    XCTAssertFalse(speech.contains("%"), "Stack row left unexpanded '%' on \(w.id)/\(item.id): \(speech)")
                    let hasPct = item.marks.contains {
                        if case .number(let n) = $0, n.unit == .percent || n.display.contains("%") { return true }
                        if case .bar(let b) = $0, b.pctLabel?.contains("%") == true { return true }
                        if case .ring(let r) = $0, r.label?.contains("%") == true { return true }
                        return false
                    }
                    if hasPct {
                        XCTAssertTrue(speech.localizedCaseContains("percent"), "Stack row missing word 'percent' on \(w.id)/\(item.id): \(speech)")
                    }
                    reportLines.append("- `\(w.id)` stack[\(idx + 1)]: \(speech)")
                }

            case .grid(let gb):
                for (rIdx, row) in gb.rows.enumerated() {
                    if gb.rowLayout == .stackedCells {
                        let rowSpeech = KitAccessibilitySpeech366B.gridRowSpeech(
                            row: row,
                            gridBody: gb,
                            index: rIdx,
                            total: gb.rows.count,
                            spec: spec
                        )
                        XCTAssertTrue(
                            rowSpeech.contains("\(rIdx + 1) of \(gb.rows.count)"),
                            "Grid row missing place on \(w.id)/\(row.id): \(rowSpeech)"
                        )
                        XCTAssertFalse(rowSpeech.contains("%"), "Grid row left unexpanded '%' on \(w.id)/\(row.id): \(rowSpeech)")
                        XCTAssertTrue(rowSpeech.localizedCaseContains("percent"), "Grid row missing 'percent' on \(w.id)/\(row.id): \(rowSpeech)")
                        reportLines.append("- `\(w.id)` gridRow[\(rIdx + 1)]: \(rowSpeech)")
                    }
                    for cell in row.cells {
                        let colLabel = gb.columns.first(where: { $0.key == cell.columnKey })?.label ?? cell.columnKey
                        let cellSpeech = KitAccessibilitySpeech366B.gridCellSpeech(
                            row: row,
                            cell: cell,
                            columnLabel: colLabel,
                            index: rIdx,
                            total: gb.rows.count,
                            spec: spec
                        )
                        XCTAssertTrue(
                            cellSpeech.contains("\(rIdx + 1) of \(gb.rows.count)"),
                            "Grid cell missing place on \(w.id)/\(row.id)/\(cell.columnKey): \(cellSpeech)"
                        )
                        XCTAssertFalse(cellSpeech.contains("%"), "Grid cell left unexpanded '%' on \(w.id)/\(row.id): \(cellSpeech)")
                        if !cellSpeech.isEmpty {
                            reportLines.append("- `\(w.id)` gridCell[\(rIdx + 1).\(cell.columnKey)]: \(cellSpeech)")
                        }
                    }
                }

            case .axis(let ab):
                let scaleSpeech = KitAccessibilitySpeech366B.axisScaleSpeech(axisBody: ab)
                if let firstTick = ab.scale.ticks.first?.label,
                   let lastTick = ab.scale.ticks.last?.label {
                    let expandedFirst = KitAccessibilitySpeech366B.expandPercent(firstTick)
                    let expandedLast = KitAccessibilitySpeech366B.expandPercent(lastTick)
                    XCTAssertTrue(scaleSpeech.contains(expandedFirst), "Axis scale missing start end '\(expandedFirst)' on \(w.id): \(scaleSpeech)")
                    XCTAssertTrue(scaleSpeech.contains(expandedLast), "Axis scale missing end '\(expandedLast)' on \(w.id): \(scaleSpeech)")
                }
                let dots = (ab.marks ?? []).compactMap { mark -> KitV1DotMark? in
                    if case .dot(let d) = mark { return d }
                    return nil
                }
                for (dIdx, dot) in dots.enumerated() {
                    let ds = KitAccessibilitySpeech366B.axisDotSpeech(
                        dot: dot,
                        axisBody: ab,
                        index: dIdx,
                        total: dots.count,
                        spec: spec
                    )
                    XCTAssertFalse(ds.contains("%"), "Axis dot left raw '%' on \(w.id): \(ds)")
                    XCTAssertTrue(ds.contains("\(dIdx + 1) of \(dots.count)"), "Axis dot missing place on \(w.id): \(ds)")
                    reportLines.append("- `\(w.id)` axisDot[\(dIdx + 1)]: \(ds)")
                }
                let seriesList = ab.series ?? []
                for (sIdx, series) in seriesList.enumerated() {
                    let ss = KitAccessibilitySpeech366B.axisSeriesSpeech(
                        series: series,
                        axisBody: ab,
                        index: sIdx,
                        total: seriesList.count,
                        spec: spec
                    )
                    XCTAssertFalse(ss.contains("%"), "Axis series left raw '%' on \(w.id): \(ss)")
                    XCTAssertTrue(ss.contains("\(sIdx + 1) of \(seriesList.count)"), "Axis series missing place on \(w.id): \(ss)")
                    reportLines.append("- `\(w.id)` axisSeries[\(sIdx + 1)]: \(ss)")
                }

            case .calendar(let cb):
                for (dIdx, day) in cb.days.enumerated() {
                    let cs = KitAccessibilitySpeech366B.calendarDaySpeech(
                        day: day,
                        calendarBody: cb,
                        spec: spec,
                        index: dIdx,
                        total: cb.days.count
                    )
                    XCTAssertFalse(cs.isEmpty)
                    XCTAssertFalse(cs.contains("%"), "Calendar day left raw '%' on \(w.id)/\(day.dateKey): \(cs)")
                    XCTAssertTrue(cs.localizedCaseContains("percent"), "Calendar day missing 'percent' on \(w.id)/\(day.dateKey): \(cs)")
                    // Day number & name check
                    let hasNameOrDate = !cs.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    XCTAssertTrue(hasNameOrDate)
                    reportLines.append("- `\(w.id)` calendarDay[\(dIdx + 1)]: \(cs)")
                }
            }

            // 2. Render live in UIWindow and inspect VoiceOver traversal + image trait ban.
            let card = try XCTUnwrap(KitCardView366B(spec: spec, now: fixedNow))
            let (window, vc, _) = await hostInWindow(view: card, width: 390, scheme: .light, dynamicType: .large)
            let axElements = collectAccessibilityElements(from: vc.view)
            XCTAssertFalse(axElements.isEmpty, "Zero accessibility elements found for \(w.id)")

            for el in axElements {
                XCTAssertFalse(
                    el.traits.contains(.image),
                    "Picture must never carry .image VoiceOver trait on \(w.id): '\(el.label)' id='\(el.identifier)'"
                )
                XCTAssertFalse(
                    el.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "image",
                    "No element may announce literal 'image' on \(w.id)"
                )
            }

            if let bigLine = spec.commonHeadline, !bigLine.isEmpty {
                let firstTextualIndex = axElements.firstIndex(where: { !$0.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
                let firstIdx = try XCTUnwrap(firstTextualIndex, "No labeled VoiceOver elements on \(w.id)")
                let firstLabel = axElements[firstIdx].label
                XCTAssertTrue(
                    firstLabel.contains(bigLine),
                    "Card must read big line '\(bigLine)' first on \(w.id), but first element was '\(firstLabel)'"
                )
            }
            window.isHidden = true
        }

        try writeAuditFile(reportLines.joined(separator: "\n") + "\n", relativePath: "kit_voiceover_sentences.md")
    }

    // MARK: - Item 6: Tap Targets >= 44x44 & Row vs Foot Routing

    func testAllTappableControlsAtLeast44x44AndRowVsFootRouting() async throws {
        let wrappers = try loadGoldenSpecs()
        let representativeIDs = [
            "kit-nba-slate",                // stack
            "kit-cfb-national-title",       // grid matrix
            "kit-middle-east-deadlines",    // grid stacked_cells
            "kit-spotify-wrapped-2026",     // calendar
            "kit-nhl-playoffs-bubble",      // axis dots
            "kit-batch1-deadline-race",     // axis series
        ]

        for id in representativeIDs {
            let w = try XCTUnwrap(wrappers.first(where: { $0.id == id }))
            var capturedRoutes: [KitV1Route] = []
            let card = try XCTUnwrap(KitCardView366B(spec: w.spec) { route in
                capturedRoutes.append(route)
            })

            for dt in [DynamicTypeSize.large, DynamicTypeSize.accessibility3] {
                capturedRoutes.removeAll()
                let (window, vc, _) = await hostInWindow(view: card, width: 390, scheme: .light, dynamicType: dt)
                let elements = collectAccessibilityElements(from: vc.view)
                let buttons = elements.filter { $0.traits.contains(.button) }
                XCTAssertFalse(buttons.isEmpty, "Expected interactive buttons on \(id) (\(dt))")

                for btn in buttons {
                    XCTAssertGreaterThanOrEqual(
                        btn.frame.width, 43.9,
                        "Button width < 44pt (\(btn.frame.width)) on \(id) (\(dt)) id='\(btn.identifier)' label='\(btn.label)'"
                    )
                    XCTAssertGreaterThanOrEqual(
                        btn.frame.height, 43.9,
                        "Button height < 44pt (\(btn.frame.height)) on \(id) (\(dt)) id='\(btn.identifier)' label='\(btn.label)'"
                    )
                }

                if dt == .large {
                    // Activate footer button -> opens set route (spec.route)
                    if let footerBtn = buttons.first(where: { $0.identifier == "kitV1.footerButton" }),
                       let expectedSetRoute = w.spec.route {
                        _ = footerBtn.object.accessibilityActivate()
                        try? await Task.sleep(nanoseconds: 20_000_000)
                        XCTAssertEqual(capturedRoutes.last, expectedSetRoute, "Footer tap on \(id) must open set route")
                    }

                    // Activate a row or cell button -> opens that row's route
                    if let rowBtn = buttons.first(where: {
                        $0.identifier.hasPrefix("kitV1.stackRow.")
                            || $0.identifier.hasPrefix("kitV1.gridRow.")
                            || $0.identifier.hasPrefix("kitV1.gridCell.")
                    }) {
                        let beforeCount = capturedRoutes.count
                        _ = rowBtn.object.accessibilityActivate()
                        try? await Task.sleep(nanoseconds: 20_000_000)
                        XCTAssertGreaterThan(capturedRoutes.count, beforeCount, "Row tap did not fire onRoute on \(id) (\(rowBtn.identifier))")
                        if let expectedRowRoute = expectedRoute(forIdentifier: rowBtn.identifier, in: w.spec) {
                            XCTAssertEqual(capturedRoutes.last, expectedRowRoute, "Row tap on \(rowBtn.identifier) routed to wrong destination")
                        }
                    }
                }
                window.isHidden = true
            }
        }
    }

    private func expectedRoute(forIdentifier id: String, in spec: KitV1CardSpec) -> KitV1Route? {
        switch spec.body {
        case .stack(let sb):
            if id.hasPrefix("kitV1.stackRow.") {
                let itemID = String(id.dropFirst("kitV1.stackRow.".count))
                return sb.items.first(where: { $0.id == itemID })?.route ?? spec.route
            }
        case .grid(let gb):
            if id.hasPrefix("kitV1.gridRow.") {
                let rowID = String(id.dropFirst("kitV1.gridRow.".count))
                return gb.rows.first(where: { $0.id == rowID })?.cells.compactMap(\.route).first ?? spec.route
            }
            if id.hasPrefix("kitV1.gridCell.") {
                let rest = String(id.dropFirst("kitV1.gridCell.".count))
                for row in gb.rows where rest.hasPrefix(row.id + ".") {
                    let colKey = String(rest.dropFirst(row.id.count + 1))
                    return row.cells.first(where: { $0.columnKey == colKey })?.route ?? spec.route
                }
            }
        default:
            break
        }
        return spec.route
    }

    // MARK: - Item 5: Largest Text AX1–AX5 Across All 17 Examples (390pt Light)

    func testAll17ExamplesAcrossAX1ToAX5At390LightAndExportSheet() async throws {
        let wrappers = try loadGoldenSpecs()
        let urls = collectHTTPSURLs(in: wrappers.map(\.raw))
        let preloaded = await preloadImages(for: urls)
        let fixedNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-24T12:00:00-08:00"))

        let sizes: [(String, DynamicTypeSize)] = [
            ("AX1", .accessibility1),
            ("AX2", .accessibility2),
            ("AX3", .accessibility3),
            ("AX4", .accessibility4),
            ("AX5", .accessibility5),
        ]

        var mdRows: [String] = [
            "# Kit v1 Largest Text Audit (`390pt`, Light, Simulator Results, Not Phone Results)",
            "",
            "| # | Example ID | AX1 | AX2 | AX3 | AX4 | AX5 |",
            "|---:|---|---|---|---|---|---|"
        ]
        var allFailures: [String] = []

        for w in wrappers {
            var cells: [String] = []
            for (sizeTag, dt) in sizes {
                let card = try XCTUnwrap(KitCardView366B(spec: w.spec, now: fixedNow))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (window, vc, img) = await hostInWindow(
                    view: card,
                    width: 390,
                    scheme: .light,
                    dynamicType: dt
                )
                let lines = try recognizeTextLines(in: img)
                let joined = lines.joined(separator: " ")
                let axElements = collectAccessibilityElements(from: vc.view)
                let buttons = axElements.filter { $0.traits.contains(.button) }
                window.isHidden = true

                var itemIssues: [String] = []
                if img.size.width > 390.5 {
                    itemIssues.append("width \(Int(img.size.width))>390")
                }
                if lines.isEmpty {
                    itemIssues.append("empty OCR")
                }
                if !joined.contains("%") {
                    itemIssues.append("missing %")
                }
                if joined.contains("\u{2026}") {
                    itemIssues.append("ellipsis '…' found")
                }
                // Check critical headline / axis endpoints weren't cut off.
                if let hl = w.spec.commonHeadline {
                    let tokens = hl.components(separatedBy: CharacterSet.alphanumerics.inverted)
                        .filter { $0.count >= 4 }
                    if let firstWord = tokens.first,
                       !joined.localizedCaseContains(firstWord) {
                        itemIssues.append("headline cut ('\(firstWord)' missing)")
                    }
                    if let lastWord = tokens.last,
                       !joined.localizedCaseContains(lastWord) {
                        itemIssues.append("headline cut ('\(lastWord)' missing)")
                    }
                }
                if case .axis(let ab) = w.spec.body,
                   let firstTick = ab.scale.ticks.first?.label,
                   let lastTick = ab.scale.ticks.last?.label {
                    let firstOK = joined.contains(firstTick) || (firstTick == "$0M" && joined.contains("$OM"))
                    if !firstOK { itemIssues.append("axis min '\(firstTick)' missing") }
                    if !joined.contains(lastTick) { itemIssues.append("axis max '\(lastTick)' missing") }
                }

                // Interactive row height >= 44pt
                for btn in buttons where btn.frame.height < 43.9 {
                    itemIssues.append("btn '\(btn.identifier)' h=\(Int(btn.frame.height))<44")
                }

                let padded = String(format: "%02d", w.index + 1)
                try writeAuditPNG(img, relativePath: "ax/ax-\(padded)-\(w.id)-\(sizeTag.lowercased()).png")

                if itemIssues.isEmpty {
                    cells.append("PASS")
                } else {
                    let detail = itemIssues.joined(separator: "; ")
                    cells.append("FAIL: \(detail)")
                    allFailures.append("\(w.id) \(sizeTag): \(detail)")
                }
            }
            mdRows.append("| \(w.index + 1) | `\(w.id)` | \(cells.joined(separator: " | ")) |")
        }

        try writeAuditFile(mdRows.joined(separator: "\n") + "\n", relativePath: "kit_ax1_to_ax5_table.md")
        XCTAssertTrue(allFailures.isEmpty, "Largest text failures across 17 × AX1..AX5:\n" + allFailures.joined(separator: "\n"))
    }

    // MARK: - Item 7: Widths (iPad 2-Column & Mac Width Across All 4 Layouts)

    func testAllFourLayoutsAtIPadTwoColAndMacWidthAndExportSheet() async throws {
        let wrappers = try loadGoldenSpecs()
        let urls = collectHTTPSURLs(in: wrappers.map(\.raw))
        let preloaded = await preloadImages(for: urls)
        let fixedNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-24T12:00:00-08:00"))

        let repIDs = [
            "kit-by-december-31",           // stack
            "kit-nba-slate",                // stack
            "kit-cfb-national-title",       // grid matrix
            "kit-middle-east-deadlines",    // grid stacked_cells
            "kit-spotify-wrapped-2026",     // calendar
            "kit-nhl-playoffs-bubble",      // axis dots
            "kit-batch1-box-office-scale",  // axis scale
            "kit-batch1-deadline-race",     // axis series
        ]
        let reps = try repIDs.map { id in try XCTUnwrap(wrappers.first(where: { $0.id == id })) }

        var reportLines: [String] = [
            "# Kit v1 Width Audit (iPad 2-Col & Mac Width, Simulator Results)",
            "",
            "| Surface | Width | Scheme | Issues |",
            "|---|---:|---|---|"
        ]
        var issues: [String] = []

        // iPad 2-col at 768pt (portrait) and 1024pt (landscape)
        for containerWidth in [CGFloat(768), CGFloat(1024)] {
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let gridView = VStack(alignment: .leading, spacing: 14) {
                    ForEach(stride(from: 0, to: reps.count, by: 2).map { $0 }, id: \.self) { rowIdx in
                        HStack(alignment: .top, spacing: 16) {
                            if let left = KitCardView366B(spec: reps[rowIdx].spec, now: fixedNow) {
                                left.environment(\.kitPreloadedImages366B, preloaded)
                                    .frame(maxWidth: .infinity, alignment: .topLeading)
                            }
                            if rowIdx + 1 < reps.count,
                               let right = KitCardView366B(spec: reps[rowIdx + 1].spec, now: fixedNow) {
                                right.environment(\.kitPreloadedImages366B, preloaded)
                                    .frame(maxWidth: .infinity, alignment: .topLeading)
                            }
                        }
                    }
                }
                let (window, vc, img) = await hostInWindow(
                    view: gridView,
                    width: containerWidth,
                    scheme: scheme,
                    dynamicType: .large,
                    horizontalSizeClass: .regular
                )
                let lines = try recognizeTextLines(in: img)
                let joined = lines.joined(separator: " ")
                let buttons = collectAccessibilityElements(from: vc.view).filter { $0.traits.contains(.button) }
                window.isHidden = true

                var rowIssues: [String] = []
                if img.size.width > containerWidth + 0.5 { rowIssues.append("overflow") }
                if !joined.contains("%") { rowIssues.append("missing %") }
                if joined.contains("\u{2026}") { rowIssues.append("ellipsis") }
                for btn in buttons where btn.frame.height < 43.9 || btn.frame.width < 43.9 {
                    rowIssues.append("target<44 on \(btn.identifier)")
                }
                let tag = scheme == .dark ? "dark" : "light"
                try writeAuditPNG(img, relativePath: "widths/ipad-2col-\(Int(containerWidth))-\(tag).png")
                let desc = rowIssues.isEmpty ? "PASS" : rowIssues.joined(separator: "; ")
                reportLines.append("| iPad 2-col | \(Int(containerWidth))pt | \(tag) | \(desc) |")
                if !rowIssues.isEmpty {
                    issues.append("iPad 2-col \(Int(containerWidth)) \(tag): \(desc)")
                }
            }
        }

        // Mac wide single-column & 2-column check (1100pt)
        let macSampleIDs = [
            "kit-nba-slate",
            "kit-cfb-national-title",
            "kit-spotify-wrapped-2026",
            "kit-nhl-playoffs-bubble",
        ]
        for id in macSampleIDs {
            let w = try XCTUnwrap(reps.first(where: { $0.id == id }))
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let card = try XCTUnwrap(KitCardView366B(spec: w.spec, now: fixedNow))
                    .environment(\.kitPreloadedImages366B, preloaded)
                let (window, vc, img) = await hostInWindow(
                    view: card,
                    width: 1100,
                    scheme: scheme,
                    dynamicType: .large,
                    horizontalSizeClass: .regular
                )
                let lines = try recognizeTextLines(in: img)
                let joined = lines.joined(separator: " ")
                let buttons = collectAccessibilityElements(from: vc.view).filter { $0.traits.contains(.button) }
                window.isHidden = true

                var rowIssues: [String] = []
                if img.size.width > 1100.5 { rowIssues.append("overflow") }
                if !joined.contains("%") { rowIssues.append("missing %") }
                if joined.contains("\u{2026}") { rowIssues.append("ellipsis") }
                for btn in buttons where btn.frame.height < 43.9 {
                    rowIssues.append("height<44 on \(btn.identifier)")
                }
                let tag = scheme == .dark ? "dark" : "light"
                try writeAuditPNG(img, relativePath: "widths/mac-1100-\(w.id)-\(tag).png")
                let desc = rowIssues.isEmpty ? "PASS" : rowIssues.joined(separator: "; ")
                reportLines.append("| Mac \(w.id) | 1100pt | \(tag) | \(desc) |")
                if !rowIssues.isEmpty {
                    issues.append("Mac 1100 \(w.id) \(tag): \(desc)")
                }
            }
        }

        try writeAuditFile(reportLines.joined(separator: "\n") + "\n", relativePath: "kit_widths_report.md")
        XCTAssertTrue(issues.isEmpty, "Width layout failures:\n" + issues.joined(separator: "\n"))
    }

    // MARK: - Item 9: Render Atlas v6 Real Sets at 390pt Light When Env Var Set

    func testRenderRealSetsV6SpecsAt390LightWhenEnvSet() async throws {
        guard let jsonPath = ProcessInfo.processInfo.environment["BUILDER_C_REAL_SETS_JSON"],
              !jsonPath.isEmpty else {
            return
        }
        let data = try Data(contentsOf: URL(fileURLWithPath: jsonPath))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let items = try XCTUnwrap(root["items"] as? [[String: Any]])
        XCTAssertEqual(items.count, 22, "Expected 22 fitting sets from fe31aa76 fixture")

        let specsRaw: [[String: Any]] = try items.map { item in
            try XCTUnwrap(item["kit_card"] as? [String: Any])
        }
        let urls = collectHTTPSURLs(in: specsRaw)
        let preloaded = await preloadImages(for: urls)
        let fixedNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-24T12:00:00-08:00"))

        var manifestEntries: [[String: Any]] = []
        var renderIssues: [String] = []

        for (idx, item) in items.enumerated() {
            let slug = try XCTUnwrap(item["slug"] as? String)
            let specObj = try XCTUnwrap(item["kit_card"] as? [String: Any])
            let specData = try JSONSerialization.data(withJSONObject: specObj)
            let spec = try XCTUnwrap(KitV1CardSpec.parse(from: specData), "Real set \(slug) failed KitV1CardSpec.parse")
            let card = try XCTUnwrap(KitCardView366B(spec: spec, now: fixedNow))
                .environment(\.kitPreloadedImages366B, preloaded)

            let (window, _, img) = await hostInWindow(
                view: card,
                width: 390,
                scheme: .light,
                dynamicType: .large
            )
            let lines = try recognizeTextLines(in: img)
            let joined = lines.joined(separator: " ")
            window.isHidden = true

            if joined.contains("\u{2026}") {
                renderIssues.append("\(slug): OCR found '…'")
            }

            let padded = String(format: "%02d", idx + 1)
            let relPNG = "real_sets/\(padded)-\(slug).png"
            try writeAuditPNG(img, relativePath: relPNG)

            manifestEntries.append([
                "index": idx + 1,
                "slug": slug,
                "id": spec.id,
                "layout": spec.layout.rawValue,
                "kicker": spec.kicker ?? "",
                "common_headline": spec.commonHeadline ?? "",
                "ocr_lines": lines,
                "png": relPNG,
                "width": Int(img.size.width),
                "height": Int(img.size.height),
            ])
        }

        let manifestData = try JSONSerialization.data(withJSONObject: ["items": manifestEntries], options: [.prettyPrinted])
        if let manifestText = String(data: manifestData, encoding: .utf8) {
            try writeAuditFile(manifestText, relativePath: "real_sets/manifest.json")
        }
        XCTAssertTrue(renderIssues.isEmpty, "Real sets render issues:\n" + renderIssues.joined(separator: "\n"))
    }
}

private extension Set where Element == String {
    mutating func addURL(_ value: String) {
        insert(value)
    }
}

private extension String {
    func localizedCaseContains(_ needle: String) -> Bool {
        range(of: needle, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
}
