import XCTest
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// #10076 — on tonight's Steelers @ Browns the iPhone Player Props card printed
/// "PASSING ATTE…" / "RUSHING ATTE…" beside a whole grey "chance of hitting":
/// the stat name and the caption shared one `HStack` at equal priority, and in
/// the paired two-column layout SwiftUI clipped the name.
///
/// The header is measured here, not described: one line where it fits, the
/// caption on its own line where it does not. The last two tests are source
/// guards on the call sites, because a correct header nobody draws is inert.
final class PropsStatNameIsNeverClipped10076Tests: XCTestCase {

    /// One column of the paired layout on an iPhone 17 (402 pt wide), measured
    /// off the 2026-10-01 simulator shot: ~354 px of 920 px displayed.
    private let pairedColumn: CGFloat = 155
    private let wide: CGFloat = 400
    private let statName = "PASSING ATTEMPTS"
    private let caption = "chance of hitting"

    private func size(_ view: some View, width: CGFloat) -> CGSize {
        let host = UIHostingController(rootView: view)
        return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    private func idealWidth(_ view: some View) -> CGFloat {
        size(view, width: .greatestFiniteMagnitude).width
    }

    private var oneLineHeight: CGFloat {
        size(PropsStatGroupHeader(label: statName, caption: nil), width: wide).height
    }

    // MARK: - The defect, measured

    /// If this fails the fix is unnecessary: name + caption on one line need
    /// more than a paired column, so the old one-line header had to clip one.
    func testNameAndCaptionDoNotFitOneLineInAPairedColumn() {
        let together = idealWidth(PropsStatGroupHeader(label: statName, caption: caption))
        XCTAssertGreaterThan(together, pairedColumn,
                             "the photographed defect: both on one line overflow the column")
    }

    /// And the name alone does fit — so wrapping the caption is enough, and the
    /// name is never the part that has to give.
    func testTheNameAloneFitsAPairedColumn() {
        let alone = idealWidth(PropsStatGroupHeader(label: statName, caption: nil))
        XCTAssertLessThanOrEqual(alone, pairedColumn)
    }

    // MARK: - The header

    func testInAPairedColumnTheCaptionMovesToItsOwnLine() {
        let h = size(PropsStatGroupHeader(label: statName, caption: caption), width: pairedColumn).height
        XCTAssertGreaterThan(h, oneLineHeight * 1.5,
                             "the caption must drop under the name, not clip it")
    }

    /// Where it fits, nothing changes: one line, as before.
    func testWhereItFitsTheHeaderStaysOneLine() {
        let h = size(PropsStatGroupHeader(label: statName, caption: caption), width: wide).height
        XCTAssertEqual(h, oneLineHeight, accuracy: 0.5)
    }

    /// The finished game's "Final N" sits on the name's line in both shapes.
    func testFinalReadoutStaysOnTheNameLine() {
        let withFinal = PropsStatGroupHeader(label: statName, caption: caption, finalText: "Final 31")
        XCTAssertEqual(size(withFinal, width: wide).height, oneLineHeight, accuracy: 0.5)
        let narrow = size(withFinal, width: pairedColumn).height
        let narrowNoFinal = size(PropsStatGroupHeader(label: statName, caption: caption), width: pairedColumn).height
        XCTAssertEqual(narrow, narrowNoFinal, accuracy: 0.5,
                       "Final N must not add a third line")
    }

    // MARK: - The card draws it (source scan)

    private func cardSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("PlayerPropsCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheScanCanSeeTheFileItIsAbout() throws {
        let source = try cardSource()
        XCTAssertGreaterThan(source.count, 5_000)
        XCTAssertTrue(source.contains("private func statGroupView"))
        XCTAssertTrue(source.contains("private func fieldView"))
    }

    /// Both captioned headers — the rung ladder and the #5176 field — go through
    /// the shared header, and neither caption is drawn as a bare `Text` beside
    /// the name any more (the shape that clipped).
    func testBothCaptionedHeadersUseTheSharedHeader() throws {
        let source = try cardSource()
        XCTAssertEqual(source.components(separatedBy: "PropsStatGroupHeader(").count - 1, 2,
                       "statGroupView and fieldView must both draw PropsStatGroupHeader")
        XCTAssertFalse(source.contains("Text(EventState.propsChanceCaption("),
                       "the ladder caption is a bare Text beside the name again — #10076")
        XCTAssertFalse(source.contains("Text(PlayerPropsField.caption("),
                       "the field caption is a bare Text beside the name again — #10076")
    }
}
