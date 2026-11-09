import ImageIO
import XCTest

/// #12314 — the layered icon for iOS 26's glass look (`AppIcon.icon`) is well
/// formed, and it is still the icon both apps name.
///
/// Xcode prefers an `AppIcon.icon` over the `AppIcon.appiconset` beside it, and
/// generates the flat iOS 17/18 icons and the Mac's from it, so a broken
/// document would break every icon at once. These read the source tree, as the
/// other source-scan tests do; the rendered look is checked on the simulator.
final class AppIcon12314Tests: XCTestCase {

    private var projectDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    private var iconDir: URL { projectDir.appendingPathComponent("Bain Luck/AppIcon.icon") }

    private func document() throws -> [String: Any] {
        let data = try Data(contentsOf: iconDir.appendingPathComponent("icon.json"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testTheDocumentParsesAndEveryImageItNamesIsInTheBundle() throws {
        let groups = try XCTUnwrap(document()["groups"] as? [[String: Any]])
        let names = groups.flatMap { group in
            (group["layers"] as? [[String: Any]] ?? []).compactMap { $0["image-name"] as? String }
        }
        XCTAssertEqual(names, ["clover.png"], "one clover layer")
        for name in names {
            let path = iconDir.appendingPathComponent("Assets").appendingPathComponent(name).path
            XCTAssertTrue(FileManager.default.fileExists(atPath: path), "missing \(name)")
        }
    }

    /// Dark gets its own background, so the Dark Home Screen never shows a
    /// white tile; the light one stays white like today's icon.
    func testTheBackgroundIsWhiteAndDarkHasItsOwn() throws {
        let fills = try XCTUnwrap(document()["fill-specializations"] as? [[String: Any]])
        let base = fills.first { $0["appearance"] == nil }?["value"] as? [String: String]
        let dark = fills.first { $0["appearance"] as? String == "dark" }?["value"] as? [String: String]
        XCTAssertEqual(base?["solid"], "extended-srgb:1.00000,1.00000,1.00000,1.00000")
        XCTAssertNotNil(dark?["solid"], "a dark background")
        XCTAssertNotEqual(dark?["solid"], base?["solid"])
    }

    /// The layer is a shape: a 1024 square whose transparent area is the
    /// background, so Clear and Tinted can draw the clover alone.
    func testTheCloverImageIsA1024SquareWithTransparency() throws {
        let url = iconDir.appendingPathComponent("Assets/clover.png")
        let source = try XCTUnwrap(CGImageSourceCreateWithURL(url as CFURL, nil))
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        XCTAssertEqual(image.width, 1024)
        XCTAssertEqual(image.height, 1024)
        XCTAssertTrue([.first, .last, .premultipliedFirst, .premultipliedLast].contains(image.alphaInfo),
                      "the clover must carry an alpha channel")
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
