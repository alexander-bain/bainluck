import CoreGraphics
import CryptoKit
import Foundation
import ImageIO
import SwiftUI
import XCTest
@testable import Bain_Luck

#if os(iOS)
import UIKit
import Vision
#endif

/// `#13767` (`423: A`) — Settings "App icon" row, picker list (`Original`, `Winter`,
/// `New Year's Eve`), build-setting synchronization, unaltered pixel hashes, and
/// `320 pt` / `.accessibility5` layout verification.
/// Original artwork supplied by Alex.
@MainActor
final class AppIconChoice423ATests: XCTestCase {

    static let expectedWinterRGBASHA256 =
        "b45d831ae42d7549ce3260beb42d49e1770a501cbba2d626da26b171db125a6b"
    static let expectedNewYearsEveRGBASHA256 =
        "0f87bcc997f80f914c8753949affc65edaef74fffb9a6ce752805302e811b9d6"

    private var projectDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private var assetsDir: URL {
        projectDir.appendingPathComponent("Bain Luck/Assets.xcassets")
    }

    // MARK: - Build Setting <-> Code List Guard

    func testAlternateAppIconBuildSettingMatchesChoiceListInDebugAndRelease() throws {
        let pbxprojURL = projectDir.appendingPathComponent("Bain Luck.xcodeproj/project.pbxproj")
        let pbxproj = try String(contentsOf: pbxprojURL, encoding: .utf8)

        let expected = AppIconChoice423A.alternateIconNames
        XCTAssertEqual(expected, ["AppIconWinter", "AppIconNewYearsEve"])

        for configMarker in ["A7869E362F525C6C000542D3 /* Debug */ = {", "A7869E372F525C6C000542D3 /* Release */ = {"] {
            let block = try XCTUnwrap(extractBuildSettingsBlock(pbxproj: pbxproj, marker: configMarker), configMarker)
            let configured = try XCTUnwrap(parseAlternateIconNames(in: block), "Missing ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES in \(configMarker)")
            XCTAssertEqual(configured, expected, "Alternate icon list drifted from build setting in \(configMarker)")
        }

        for name in expected {
            let iconSetURL = assetsDir.appendingPathComponent("\(name).appiconset")
            var isDir: ObjCBool = false
            XCTAssertTrue(FileManager.default.fileExists(atPath: iconSetURL.path, isDirectory: &isDir) && isDir.boolValue, "Missing \(name).appiconset")
            XCTAssertTrue(FileManager.default.fileExists(atPath: iconSetURL.appendingPathComponent("Contents.json").path))
        }

        for choice in AppIconChoice423A.allCases {
            let previewURL = assetsDir.appendingPathComponent("\(choice.previewAssetName).imageset")
            var isDir: ObjCBool = false
            XCTAssertTrue(FileManager.default.fileExists(atPath: previewURL.path, isDirectory: &isDir) && isDir.boolValue, "Missing \(choice.previewAssetName).imageset")
        }
    }

    // MARK: - Asset Integrity & Unaltered Pixel Verification

    func testAlternateIconAssetsAreOpaqueRGBMatchingVerifiedHashesAndGrayscaleTinted() throws {
        let specs: [(setName: String, expectedSHA: String)] = [
            ("AppIconWinter.appiconset", Self.expectedWinterRGBASHA256),
            ("AppIconNewYearsEve.appiconset", Self.expectedNewYearsEveRGBASHA256),
        ]

        for spec in specs {
            let dir = assetsDir.appendingPathComponent(spec.setName)
            for filename in ["icon_1024.png", "icon_1024_dark.png"] {
                let info = try inspectPNG(at: dir.appendingPathComponent(filename))
                XCTAssertEqual(info.width, 1024, "\(spec.setName)/\(filename)")
                XCTAssertEqual(info.height, 1024, "\(spec.setName)/\(filename)")
                XCTAssertEqual(info.colorType, 2, "Must be 24-bit opaque RGB without alpha: \(spec.setName)/\(filename)")
                let sha = try rgbaSHA256(of: info.cgImage)
                XCTAssertEqual(sha, spec.expectedSHA, "Pixel hash mismatch: \(spec.setName)/\(filename)")
            }

            let tintedInfo = try inspectPNG(at: dir.appendingPathComponent("icon_1024_tinted.png"))
            XCTAssertEqual(tintedInfo.width, 1024)
            XCTAssertEqual(tintedInfo.height, 1024)
            XCTAssertEqual(tintedInfo.colorType, 2, "Tinted slot must be opaque 24-bit RGB without alpha")
            let rawData = try XCTUnwrap(tintedInfo.cgImage.dataProvider?.data as Data?)
            let bpr = tintedInfo.cgImage.bytesPerRow
            let bpp = tintedInfo.cgImage.bitsPerPixel / 8
            rawData.withUnsafeBytes { rawBuf in
                let base = rawBuf.bindMemory(to: UInt8.self).baseAddress!
                for y in stride(from: 0, to: tintedInfo.height, by: 8) {
                    let row = base.advanced(by: y * bpr)
                    for x in stride(from: 0, to: tintedInfo.width, by: 8) {
                        let i = x * bpp
                        XCTAssertEqual(row[i], row[i + 1])
                        XCTAssertEqual(row[i + 1], row[i + 2])
                    }
                }
            }
        }
    }

    func testReaderFacingNamesMatchRuling423A() {
        XCTAssertEqual(
            AppIconChoice423A.allCases.map(\.displayName),
            ["Original", "Winter", "New Year's Eve"]
        )
        XCTAssertNil(AppIconChoice423A.original.alternateIconName)
        XCTAssertEqual(AppIconChoice423A.from(alternateIconName: nil), .original)
        XCTAssertEqual(AppIconChoice423A.from(alternateIconName: "AppIconWinter"), .winter)
        XCTAssertEqual(AppIconChoice423A.from(alternateIconName: "AppIconNewYearsEve"), .newYearsEve)
        XCTAssertEqual(AppIconChoice423A.from(alternateIconName: "UnknownSet"), .original)
    }

    // MARK: - Switching Logic & Bundle Info.plist

    #if os(iOS)
    func testCompiledBundleDeclaresBothAlternateIconsAndSwitcherWorksBothWays() async throws {
        XCTAssertTrue(UIApplication.shared.supportsAlternateIcons)

        let bundleIcons = try XCTUnwrap(Bundle.main.infoDictionary?["CFBundleIcons"] as? [String: Any])
        let alternates = try XCTUnwrap(bundleIcons["CFBundleAlternateIcons"] as? [String: Any])
        XCTAssertEqual(Set(alternates.keys), Set(AppIconChoice423A.alternateIconNames))

        var current: String? = nil
        var calls: [String?] = []
        let switcher = AppIconSwitcher423A(
            supportsAlternateIcons: { true },
            currentIconName: { current },
            setIconName: { name in
                calls.append(name)
                current = name
            }
        )

        // No-op when selecting already active choice
        let same = try await switcher.select(.original)
        XCTAssertEqual(same, .original)
        XCTAssertTrue(calls.isEmpty)

        // Switch Original -> Winter -> New Year's Eve -> Original (nil)
        let winterSelected = try await switcher.select(.winter)
        let nyeSelected = try await switcher.select(.newYearsEve)
        let originalRestored = try await switcher.select(.original)
        XCTAssertEqual(winterSelected, .winter)
        XCTAssertEqual(nyeSelected, .newYearsEve)
        XCTAssertEqual(originalRestored, .original)
        XCTAssertEqual(calls, ["AppIconWinter", "AppIconNewYearsEve", nil])

        // Error preserves prior active choice
        struct SwitchFailure: Error {}
        current = "AppIconWinter"
        let failingSwitcher = AppIconSwitcher423A(
            supportsAlternateIcons: { true },
            currentIconName: { current },
            setIconName: { _ in throw SwitchFailure() }
        )
        do {
            _ = try await failingSwitcher.select(.newYearsEve)
            XCTFail("Expected switch failure to throw")
        } catch is SwitchFailure {
            XCTAssertEqual(failingSwitcher.activeChoice, .winter)
        }
    }

    func testSettingsRowAndPickerFitAt390And320AndLargestTextInLightAndDark() throws {
        let outDir = ProcessInfo.processInfo.environment["EXPORT_13767_UI_DIR"]
        let variants: [(name: String, width: CGFloat, style: UIUserInterfaceStyle, scheme: ColorScheme, dynamicType: DynamicTypeSize, uiSize: UIContentSizeCategory, height: CGFloat)] = [
            ("390_light", 390, .light, .light, .large, .large, 844),
            ("390_dark", 390, .dark, .dark, .large, .large, 844),
            ("320_ax5_light", 320, .light, .light, .accessibility5, .accessibilityExtraExtraExtraLarge, 1850),
            ("320_ax5_dark", 320, .dark, .dark, .accessibility5, .accessibilityExtraExtraExtraLarge, 1850),
        ]

        let signedOutAuth = AuthManager()
        signedOutAuth.user = nil
        let nav = NavigationCoordinator()

        let mockWinterSwitcher = AppIconSwitcher423A(
            supportsAlternateIcons: { true },
            currentIconName: { "AppIconWinter" },
            setIconName: { _ in }
        )

        for v in variants {
            let prefsView = NavigationStack {
                PreferencesView(appIconSwitcherForTest: mockWinterSwitcher)
            }
            .environmentObject(signedOutAuth)
            .environmentObject(nav)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, v.scheme)

            let prefsImg = Self.renderPhoneView(
                prefsView,
                width: v.width,
                height: v.height,
                style: v.style,
                dynamicType: v.dynamicType,
                contentSize: v.uiSize
            )
            let prefsOCR = try Self.recognizeText(in: XCTUnwrap(prefsImg.cgImage))
            let flatPrefsOCR = prefsOCR.replacingOccurrences(of: " | ", with: " ")
            XCTAssertTrue(flatPrefsOCR.localizedCaseInsensitiveContains("App icon"), "\(v.name) row missing 'App icon': \(prefsOCR)")
            XCTAssertTrue(
                flatPrefsOCR.localizedCaseInsensitiveContains("Winter") || flatPrefsOCR.localizedCaseInsensitiveContains("Ninter"),
                "\(v.name) row missing active 'Winter': \(prefsOCR)"
            )
            XCTAssertFalse(prefsOCR.contains("App icon...") || prefsOCR.contains("App icon…") || prefsOCR.contains("Winter...") || prefsOCR.contains("Winter…"), "\(v.name) row truncated: \(prefsOCR)")
            if v.width >= 390 {
                XCTAssertFalse(prefsOCR.contains("…") || prefsOCR.contains("..."), "\(v.name) Preferences truncated: \(prefsOCR)")
            }

            let pickerView = NavigationStack {
                AppIconPickerView423A(switcher: mockWinterSwitcher)
            }
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, v.scheme)

            let pickerHeight: CGFloat = v.dynamicType.isAccessibilitySize ? 720 : 480
            let pickerImg = Self.renderPhoneView(
                pickerView,
                width: v.width,
                height: pickerHeight,
                style: v.style,
                dynamicType: v.dynamicType,
                contentSize: v.uiSize
            )
            let pickerOCR = try Self.recognizeText(in: XCTUnwrap(pickerImg.cgImage))
            let flatPickerOCR = pickerOCR.replacingOccurrences(of: " | ", with: " ")
            for name in ["Original", "Winter", "New Year's Eve"] {
                if name == "Winter" && v.dynamicType.isAccessibilitySize {
                    // Vision OCR occasionally reads giant AX5 'W' as 'N' ("Ninter").
                    XCTAssertTrue(
                        flatPickerOCR.localizedCaseInsensitiveContains("Winter") || flatPickerOCR.localizedCaseInsensitiveContains("Ninter"),
                        "\(v.name) picker missing 'Winter': \(pickerOCR)"
                    )
                } else {
                    XCTAssertTrue(flatPickerOCR.localizedCaseInsensitiveContains(name), "\(v.name) picker missing '\(name)': \(pickerOCR)")
                }
            }
            XCTAssertFalse(pickerOCR.contains("…") || pickerOCR.contains("...") || pickerOCR.contains("-"), "\(v.name) picker truncated or hyphenated: \(pickerOCR)")

            if let outDir, !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                try XCTUnwrap(prefsImg.pngData()).write(to: dirURL.appendingPathComponent("row_\(v.name).png"))
                try XCTUnwrap(pickerImg.pngData()).write(to: dirURL.appendingPathComponent("picker_\(v.name).png"))
            }
        }
    }
    #endif

    // MARK: - Helpers

    private func extractBuildSettingsBlock(pbxproj: String, marker: String) -> String? {
        guard let markerRange = pbxproj.range(of: marker) else { return nil }
        guard let endRange = pbxproj.range(of: "name = ", range: markerRange.upperBound..<pbxproj.endIndex) else { return nil }
        return String(pbxproj[markerRange.upperBound..<endRange.lowerBound])
    }

    private func parseAlternateIconNames(in block: String) -> [String]? {
        guard let keyRange = block.range(of: "ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = ") else {
            return nil
        }
        let rest = block[keyRange.upperBound...]
        if rest.first == "(" {
            guard let close = rest.firstIndex(of: ")"), let semi = rest.range(of: ";", range: close..<rest.endIndex) else {
                return nil
            }
            _ = semi
            let inner = rest[rest.index(after: rest.startIndex)..<close]
            return inner
                .split(whereSeparator: { $0 == "," || $0.isWhitespace || $0.isNewline })
                .map { String($0).trimmingCharacters(in: CharacterSet(charactersIn: "\"")) }
                .filter { !$0.isEmpty }
        } else {
            guard let semi = rest.firstIndex(of: ";") else { return nil }
            let single = String(rest[..<semi]).trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "\"")))
            return single.isEmpty ? [] : [single]
        }
    }

    private func inspectPNG(at url: URL) throws -> (width: Int, height: Int, colorType: UInt8, cgImage: CGImage) {
        let data = try Data(contentsOf: url)
        XCTAssertGreaterThan(data.count, 30, "PNG too small: \(url.lastPathComponent)")
        let colorType = data[25]
        let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
        let cg = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        return (cg.width, cg.height, colorType, cg)
    }

    private func rgbaSHA256(of cgImage: CGImage) throws -> String {
        let width = cgImage.width
        let height = cgImage.height
        let bytesPerPixel = cgImage.bitsPerPixel / 8
        XCTAssertTrue(bytesPerPixel == 3 || bytesPerPixel == 4, "Unexpected pixel stride: \(cgImage.bitsPerPixel)")
        XCTAssertTrue(cgImage.alphaInfo == .none || cgImage.alphaInfo == .noneSkipLast)
        let rawData = try XCTUnwrap(cgImage.dataProvider?.data as Data?)
        let bytesPerRow = cgImage.bytesPerRow
        var rgba = Data(capacity: width * height * 4)
        rawData.withUnsafeBytes { rawBuf in
            let base = rawBuf.bindMemory(to: UInt8.self).baseAddress!
            for y in 0..<height {
                let row = base.advanced(by: y * bytesPerRow)
                for x in 0..<width {
                    let i = x * bytesPerPixel
                    rgba.append(row[i])
                    rgba.append(row[i + 1])
                    rgba.append(row[i + 2])
                    rgba.append(255)
                }
            }
        }
        return SHA256.hash(data: rgba).map { String(format: "%02x", $0) }.joined()
    }

    #if os(iOS)
    private static func renderPhoneView<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        style: UIUserInterfaceStyle,
        dynamicType: DynamicTypeSize,
        contentSize: UIContentSizeCategory
    ) -> UIImage {
        let host = hostForMeasurement(view, at: dynamicType)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = style
        host.traitOverrides.horizontalSizeClass = .compact
        host.traitOverrides.preferredContentSizeCategory = contentSize
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = bounds

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: bounds)
        }
        window.frame = bounds
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let deadline = Date().addingTimeInterval(0.25)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < deadline

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private static func recognizeText(in cgImage: CGImage) throws -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? [])
            .compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: " | ")
    }
    #endif
}
