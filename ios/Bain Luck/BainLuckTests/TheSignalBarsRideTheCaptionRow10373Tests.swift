import XCTest
@testable import Bain_Luck

/// #10373 — Alex, rage shake 169: the signal bars and the share button on the
/// Discover game card sat on a row of their own under the caption, adding about a
/// row of empty height to every game card. They now trail the caption on its row;
/// only accessibility text sizes (and a card with no caption) keep the own row.
///
/// The layout is pinned at the source because the arrangement IS the fix: a
/// revert to a free-standing footer `HStack { Spacer() … }` after the caption
/// compiles and renders, and nothing else in the suite measures card height.
final class TheSignalBarsRideTheCaptionRow10373Tests: XCTestCase {
    private func source() throws -> String {
        let path = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/DiscoverEventCard.swift")
        return try String(contentsOf: path, encoding: .utf8)
    }

    private func squashed(_ text: String) -> String {
        text.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
    }

    func testAtStandardSizesTheMarksShareTheCaptionsRow() throws {
        let s = squashed(try source())
        XCTAssertTrue(
            s.contains("} else { HStack(alignment: .center, spacing: 8) { contextCaption(contextText) footerMarks } }"),
            "the caption and the footer marks must be ONE row at standard text sizes"
        )
    }

    func testOnlyAccessibilitySizesOrACaptionlessCardKeepTheOwnRow() throws {
        let s = squashed(try source())
        XCTAssertTrue(s.contains(
            "if let contextText { if dynamicTypeSize.isAccessibilitySize { contextCaption(contextText) HStack { Spacer() footerMarks } }"
        ))
        XCTAssertTrue(s.contains("} else { HStack { Spacer() footerMarks } }"))
        // Exactly the two fallbacks above draw a free-standing marks row — a third
        // is the regression this file exists for.
        XCTAssertEqual(s.components(separatedBy: "HStack { Spacer() footerMarks }").count - 1, 2)
    }

    func testThereIsOneFooterDefinition() throws {
        let s = try source()
        // One ShareLink and one SignalBarsView on the card: the two layouts call
        // the same `footerMarks`, so they cannot draw two different footers.
        XCTAssertEqual(s.components(separatedBy: "ShareLink(").count - 1, 1)
        XCTAssertEqual(s.components(separatedBy: "SignalBarsView(tier: event.confidenceTier)").count - 1, 1)
        // The 44pt tap target is kept — the row it shares is the caption's.
        XCTAssertTrue(s.contains(".frame(minWidth: 44, minHeight: 44)"))
    }
}
