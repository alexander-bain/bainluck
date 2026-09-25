import XCTest
@testable import Bain_Luck

/// #8517 — **the phone calls the accuracy screen what the website calls it.**
///
/// The website retired "Calibration" as a reader label in #7738: its footer
/// link and tab/share title read "Accuracy". The phone still printed
/// "Calibration" as the screen's title, on the Browse card that opens it and
/// in the iPad sidebar. All three now read `CalibrationView.readerTitle`.
final class TheAccuracyScreenIsCalledAccuracy8517Tests: XCTestCase {

    private static var testsDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    }

    /// Code only — comments stripped, so a doc comment that names the old word
    /// to explain why it is gone cannot fail the scan.
    private static func code(of url: URL) throws -> String {
        try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    private static func appCode(_ relativePath: String) throws -> String {
        try code(of: testsDir.deletingLastPathComponent()
            .appendingPathComponent("Bain Luck").appendingPathComponent(relativePath))
    }

    func testTheReaderTitleIsTheWebsitesWord() throws {
        XCTAssertEqual(CalibrationView.readerTitle, "Accuracy")
        // The web half, read from the repo, so the two cannot drift apart
        // silently: `frontend/app/calibration/layout.tsx`'s metadata title.
        let repoRoot = Self.testsDir.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let layout = try Self.code(of: repoRoot
            .appendingPathComponent("frontend/app/calibration/layout.tsx"))
        XCTAssertTrue(layout.contains("title: \"\(CalibrationView.readerTitle)\""),
                      "web's accuracy page title no longer matches the phone's label")
    }

    /// Every place a reader meets the screen reads the one constant, and none
    /// of them prints the retired word.
    func testNoReaderLabelSaysCalibration() throws {
        let sites: [(file: String, uses: String)] = [
            ("Views/CalibrationView.swift", ".navigationTitle(CalibrationView.readerTitle)"),
            ("Views/LeaguesView.swift", "title: CalibrationView.readerTitle,"),
            ("Views/MainTabView.swift", "sidebarLabel(CalibrationView.readerTitle,"),
        ]
        for site in sites {
            let code = try Self.appCode(site.file)
            XCTAssertTrue(code.contains(site.uses), "\(site.file) no longer reads the reader title")
            XCTAssertFalse(code.contains(".navigationTitle(\"Calibration\")"), site.file)
            XCTAssertFalse(code.contains("title: \"Calibration\""), site.file)
            XCTAssertFalse(code.contains("sidebarLabel(\"Calibration\""), site.file)
        }
    }
}
