import CoreGraphics
import CryptoKit
import Foundation
import ImageIO
import XCTest

/// #13633 / #12314 (rulings 382: B & 390: A) — app icons use the whole clover
/// drawing (original artwork supplied by Alex) as opaque RGB; the in-app
/// `BainLuckMark` uses the transparent RGBA clover-and-shadow drawing (`390: A`).
final class AppIcon12314Tests: XCTestCase {

    static let expectedSourceRGBASHA256 =
        "620805dcaf0cd80539bdf66d2296ddec8946dedc9dde17a8a5aa6a811147ec59"
    /// Source Mac file `handoffs/logo-382b/clover-mark-transparent-1024.png`
    /// (corrected 12:41 PM PT) SHA-256 `e858f5467c41677f4694cd696ffd156da12514bd578be487bb6d9bb127959629`;
    /// straight RGBA SHA-256 is `31f17291a0e40243ee10060fb1312dc260d8c199971765d7e71868c96ea28f3a`.
    /// ImageIO decodes PNGs as premultiplied RGBA, whose exact byte hash is below.
    static let expectedTransparentMarkPremulRGBASHA256 =
        "33d93a2cbc2174391f00d9a5a75cba318d7ed9a1d3306030fc3d71bc7631fc7b"

    private var projectDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    private var iosIconSetDir: URL {
        projectDir.appendingPathComponent("Bain Luck/Assets.xcassets/AppIcon.appiconset")
    }

    private var watchIconSetDir: URL {
        projectDir.appendingPathComponent("BainLuckWatch Watch App/Assets.xcassets/AppIcon.appiconset")
    }

    private var markImageSetDir: URL {
        projectDir.appendingPathComponent("Bain Luck/Assets.xcassets/BainLuckMark.imageset")
    }

    private func inspectPNG(at url: URL) throws -> (width: Int, height: Int, colorType: UInt8, cgImage: CGImage) {
        let data = try Data(contentsOf: url)
        XCTAssertGreaterThan(data.count, 30, "PNG too small: \(url.lastPathComponent)")
        let pngSig: [UInt8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        XCTAssertEqual(Array(data.prefix(8)), pngSig, "Not a PNG: \(url.lastPathComponent)")
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
        XCTAssertTrue(
            cgImage.alphaInfo == .none || cgImage.alphaInfo == .noneSkipLast,
            "Unexpected alpha info: \(cgImage.alphaInfo.rawValue)"
        )
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

    func testLayeredAppIconBundleRemovedSoFlattenedIconSetCompilesUnaltered() {
        let layeredIconDir = projectDir.appendingPathComponent("Bain Luck/AppIcon.icon").path
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: layeredIconDir),
            "AppIcon.icon must be absent so Xcode compiles AppIcon.appiconset without added effects"
        )
    }

    func testColor1024AppIconsAreFlattenedRGBAndMatchVerifiedPixelHash() throws {
        let targets: [URL] = [
            iosIconSetDir.appendingPathComponent("icon_1024.png"),
            iosIconSetDir.appendingPathComponent("icon_1024_dark.png"),
            watchIconSetDir.appendingPathComponent("icon_1024.png"),
        ]
        for url in targets {
            let info = try inspectPNG(at: url)
            XCTAssertEqual(info.width, 1024, url.lastPathComponent)
            XCTAssertEqual(info.height, 1024, url.lastPathComponent)
            XCTAssertEqual(info.colorType, 2, "Must be flattened 24-bit RGB with no alpha: \(url.lastPathComponent)")
            let sha = try rgbaSHA256(of: info.cgImage)
            XCTAssertEqual(sha, Self.expectedSourceRGBASHA256, "Pixel hash mismatch: \(url.path)")
        }
    }

    func testInAppMarkIsTransparentRGBAWithoutMetadataAndMatchesVerifiedPixelHash() throws {
        let url = markImageSetDir.appendingPathComponent("bainluck_mark_1024.png")
        let raw = try Data(contentsOf: url)
        let info = try inspectPNG(at: url)
        XCTAssertEqual(info.width, 1024)
        XCTAssertEqual(info.height, 1024)
        XCTAssertEqual(info.colorType, 6, "BainLuckMark must be RGBA with clear alpha (390: A)")

        var pos = 8
        var chunkTypes: [String] = []
        while pos + 8 <= raw.count {
            let len = Int(raw[pos]) << 24 | Int(raw[pos + 1]) << 16 | Int(raw[pos + 2]) << 8 | Int(raw[pos + 3])
            let ctype = String(bytes: raw[(pos + 4)..<(pos + 8)], encoding: .isoLatin1) ?? ""
            chunkTypes.append(ctype)
            pos += 12 + len
        }
        XCTAssertFalse(chunkTypes.contains("caBX"), "Metadata chunk must be stripped")
        for unexpected in ["eXIf", "tEXt", "zTXt", "iTXt"] {
            XCTAssertFalse(chunkTypes.contains(unexpected), "Unexpected chunk \(unexpected)")
        }

        let width = info.width
        let height = info.height
        let rawProvider = try XCTUnwrap(info.cgImage.dataProvider?.data as Data?)
        let bpp = info.cgImage.bitsPerPixel / 8
        let rowStride = info.cgImage.bytesPerRow
        XCTAssertEqual(bpp, 4)
        var unpremul = Data(capacity: width * height * 4)
        var clearPixelCount = 0
        rawProvider.withUnsafeBytes { rawBuf in
            let base = rawBuf.bindMemory(to: UInt8.self).baseAddress!
            for y in 0..<height {
                let row = base.advanced(by: y * rowStride)
                for x in 0..<width {
                    let i = x * 4
                    let a = row[i + 3]
                    if a == 0 { clearPixelCount += 1 }
                    unpremul.append(row[i])
                    unpremul.append(row[i + 1])
                    unpremul.append(row[i + 2])
                    unpremul.append(a)
                }
            }
        }
        XCTAssertGreaterThan(clearPixelCount, 400_000, "Transparent mark background must be clear")
        let sha = SHA256.hash(data: unpremul).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(sha, Self.expectedTransparentMarkPremulRGBASHA256)
    }

    func testOneColorTintedIconIsGrayscaleOfDrawingWithoutAlpha() throws {
        let url = iosIconSetDir.appendingPathComponent("icon_1024_tinted.png")
        let info = try inspectPNG(at: url)
        XCTAssertEqual(info.width, 1024)
        XCTAssertEqual(info.height, 1024)
        XCTAssertEqual(info.colorType, 2, "Must have no alpha channel")
        let rawData = try XCTUnwrap(info.cgImage.dataProvider?.data as Data?)
        let bytesPerRow = info.cgImage.bytesPerRow
        let bytesPerPixel = info.cgImage.bitsPerPixel / 8
        rawData.withUnsafeBytes { rawBuf in
            let base = rawBuf.bindMemory(to: UInt8.self).baseAddress!
            for y in stride(from: 0, to: info.height, by: 8) {
                let row = base.advanced(by: y * bytesPerRow)
                for x in stride(from: 0, to: info.width, by: 8) {
                    let i = x * bytesPerPixel
                    XCTAssertEqual(row[i], row[i + 1])
                    XCTAssertEqual(row[i + 1], row[i + 2])
                }
            }
        }
    }

    func testSmallerMacIconSizesArePresentAtExactDimensionsWithoutAlpha() throws {
        let expected: [(String, Int)] = [
            ("icon_16x16.png", 16),
            ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32),
            ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512),
            ("icon_512x512@2x.png", 1024),
        ]
        for (filename, px) in expected {
            let info = try inspectPNG(at: iosIconSetDir.appendingPathComponent(filename))
            XCTAssertEqual(info.width, px, filename)
            XCTAssertEqual(info.height, px, filename)
            XCTAssertEqual(info.colorType, 2, "Must have no alpha: \(filename)")
        }
    }

    func testInAppBrandMarkScreensUseBainLuckMarkViewInsteadOfEmoji() throws {
        let replacedScreens = [
            "Bain Luck/Views/WelcomeView.swift",
            "Bain Luck/Views/MyStuffView.swift",
            "Bain Luck/Views/MainTabView.swift",
            "Bain Luck/Views/FeedView.swift",
            "Bain Luck/Components/TelemetryConsentPrompt.swift",
        ]
        for rel in replacedScreens {
            let text = try String(contentsOf: projectDir.appendingPathComponent(rel), encoding: .utf8)
            XCTAssertFalse(text.contains("🍀"), "Unexpected clover emoji remaining in \(rel)")
            XCTAssertFalse(text.lowercased().contains("\\u{1f340}"), "Unexpected clover Unicode escape remaining in \(rel)")
            XCTAssertTrue(text.contains("BainLuckMarkView("), "Expected BainLuckMarkView in \(rel)")
        }
        let share = try String(
            contentsOf: projectDir.appendingPathComponent("Bain Luck/Utilities/ShareCardRenderer.swift"),
            encoding: .utf8
        )
        XCTAssertEqual(share.components(separatedBy: "BainLuckMarkView(").count - 1, 2)
        XCTAssertEqual(share.components(separatedBy: "BainLuckMarkView(size: 20)").count - 1, 2)
        let footerLines = share.components(separatedBy: "\n").filter { $0.contains("bainluck.com") || $0.contains("🍀") }
        XCTAssertEqual(footerLines.filter { $0.contains("🍀") && !$0.contains("default:") }.count, 0)

        let watchHome = try String(
            contentsOf: projectDir.appendingPathComponent("BainLuckWatch Watch App/WatchHomeView.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(watchHome.contains("🍀"))
    }

    /// Same name as the asset-catalog set, so no build setting changed: both
    /// apps still name `AppIcon` in Debug and Release.
    func testBothAppsStillNameAppIconInDebugAndRelease() throws {
        let project = try String(
            contentsOf: projectDir.appendingPathComponent("Bain Luck.xcodeproj/project.pbxproj"),
            encoding: .utf8)
        XCTAssertEqual(project.components(separatedBy: "ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;").count - 1, 4)
        XCTAssertFalse(project.contains("ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon.icon"))
    }
}
