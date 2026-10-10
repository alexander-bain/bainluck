import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #4395 — at the accessibility text sizes the Championship Path cut words it
/// had room to wrap: "World Series" drew as `World…` on both cards while
/// "Play-offs" beside it wrapped, and the team code broke mid-word beside its
/// logo (`CH` / `W`). No `Text` there carries a `lineLimit`; the label was
/// simply laid out shorter than its own wrapped text.
///
/// The claim is about what each word DREW, so this hosts the shipped
/// `ChampionshipPathView` in a window — the cards' width arrives through a
/// preference, a second layout pass an unhosted render never takes — and reads
/// the frames of the layers SwiftUI draws text into (one `CGDrawingLayer` per
/// `Text`; a hosted SwiftUI tree publishes no accessibility elements to a unit
/// test, so those frames are the laid-out text). Each label is then rendered
/// ALONE at the card's width and text size, free to wrap: a whole label draws a
/// layer exactly that size; a label cut to `World…` draws a different one.
@MainActor
final class ChampionshipPathWordsStayWhole4395Tests: XCTestCase {

    /// The screen minus the event page's 16 pt margin each side. 375 pt SE —
    /// the narrowest supported phone — and 402 pt iPhone 17, #4395's re-shoot.
    private static let seWidth: CGFloat = 375 - 32
    private static let iPhone17Width: CGFloat = 402 - 32

    /// A layer lands on the device's 1/3 pt grid; the reference is rendered at
    /// 3x as well, so the two agree to within one pixel.
    private static let epsilon: CGFloat = 0.34

    /// CHW @ HOU (`15320300`), the page #4395 was re-photographed on, stages as
    /// served. `logo_url` is omitted so the header does not wait on a network
    /// image; the placeholder is the same 40 pt square.
    /// #10830 — `awayOnly` is the page that still draws the per-team CARD (a
    /// two-team page is the aligned season table, `SeasonComparisonView`).
    private static func progression(awayOnly: Bool = false) throws -> TeamProgressionResponse {
        var json = #"""
        {"event_id": 15320300, "league": "baseball_mlb", "league_name": "MLB",
         "away_team": {"name": "Chicago White Sox", "short_name": "CHW", "record": "84-78",
                       "conference": "American League",
                       "stages": [
                         {"key": "playoffs", "label": "Make Playoffs", "probability": 1.0},
                         {"key": "division", "label": "Division", "probability": null},
                         {"key": "world_series", "label": "World Series", "probability": 0.03}
                       ]},
         "home_team": {"name": "Houston Astros", "short_name": "HOU", "record": "81-81",
                       "conference": "American League",
                       "stages": [
                         {"key": "playoffs", "label": "Make Playoffs", "probability": 1.0},
                         {"key": "division", "label": "Division", "probability": 1.0},
                         {"key": "world_series", "label": "World Series", "probability": 0.019}
                       ]}}
        """#
        if awayOnly, let home = json.range(of: #""home_team""#),
           let comma = json[..<home.lowerBound].lastIndex(of: ",") {
            json = String(json[..<comma]) + "}"
        }
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(TeamProgressionResponse.self, from: Data(json.utf8))
    }

    /// The frame of every text layer in the hosted view, in window coordinates.
    private struct Hosted {
        let host: UIViewController
        let window: UIWindow

        var textFrames: [CGRect] {
            var found: [CGRect] = []
            func walk(_ layer: CALayer) {
                if String(describing: type(of: layer)).contains("CGDrawingLayer") {
                    found.append(layer.convert(layer.bounds, to: window.layer))
                }
                layer.sublayers?.forEach(walk)
            }
            walk(host.view.layer)
            return found
        }

        func frames(sized size: CGSize) -> [CGRect] {
            textFrames.filter {
                abs($0.width - size.width) <= epsilon && abs($0.height - size.height) <= epsilon
            }
        }
    }

    private func hosted(width: CGFloat, at size: DynamicTypeSize, awayOnly: Bool = false) throws -> Hosted {
        let view = ChampionshipPathView(progression: try Self.progression(awayOnly: awayOnly))
            .frame(width: width)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        let host = hostForMeasurement(view, at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 4000))
        window.rootViewController = host
        window.isHidden = false
        host.view.frame = window.bounds
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }
        return Hosted(host: host, window: window)
    }

    /// The width the one-team card gives its rows: the view's own 16 pt padding
    /// each side, then `ChampionshipRowLayout`'s card insets.
    private static func cardContentWidth(_ width: CGFloat) -> CGFloat {
        ChampionshipRowLayout.teamCardContentWidth(totalWidth: width - 32, cardCount: 1)
    }

    /// The size `text` draws at when it may wrap freely within `width`.
    private func drawnSize<V: View>(
        _ text: V, within width: CGFloat?, at size: DynamicTypeSize
    ) throws -> CGSize {
        let renderer = rendererForMeasurement(
            text.fixedSize(horizontal: width == nil, vertical: true), at: size)
        renderer.proposedSize = ProposedViewSize(width: width, height: nil)
        renderer.scale = 3
        return try XCTUnwrap(renderer.uiImage).size
    }

    private func stageLabel(_ s: String) -> some View {
        Text(s).font(.caption)
    }

    private func teamName(_ s: String) -> some View {
        Text(s).font(.subheadline).fontWeight(.bold)
    }

    private func describe(_ frames: [CGRect]) -> String {
        frames.map { "(\($0.minX), \($0.minY)) \($0.width)×\($0.height)" }.joined(separator: "; ")
    }

    // MARK: - The stage labels

    private func assertStageLabelsWhole(
        width: CGFloat, at size: DynamicTypeSize,
        file: StaticString = #filePath, line: UInt = #line
    ) throws {
        // The one-team page: the card.
        let card = try hosted(width: width, at: size, awayOnly: true)
        let column = Self.cardContentWidth(width)
        for label in ["Make Playoffs", "World Series"] {
            let whole = try drawnSize(stageLabel(label), within: column, at: size)
            let found = card.frames(sized: whole)
            XCTAssertEqual(
                found.count, 1,
                """
                at \(size) on \(width)pt '\(label)' wrapped whole in a \(column)pt card \
                draws \(whole.width)×\(whole.height); expected one such layer, \
                found \(found.count). Text layers: \(describe(card.textFrames))
                """,
                file: file, line: line)
        }

        // #10830 — the two-team page: the aligned table. At the accessibility
        // sizes its label takes its own line across the table's whole width.
        let table = try hosted(width: width, at: size)
        for label in ["Make Playoffs", "World Series"] {
            let whole = try drawnSize(tableLabel(label), within: width - 32, at: size)
            XCTAssertEqual(
                table.frames(sized: whole).count, 1,
                """
                at \(size) on \(width)pt the table's '\(label)' should draw whole across \
                \(width - 32)pt as \(whole.width)×\(whole.height). Text layers: \
                \(describe(table.textFrames))
                """,
                file: file, line: line)
        }
    }

    /// The table's stage label: `SeasonComparisonView.label`'s font.
    private func tableLabel(_ s: String) -> some View {
        Text(s).font(.subheadline)
    }

    /// Not vacuous: at this size "World Series" cannot sit on one line in a
    /// third of the table — the column a side-by-side row would give it — which
    /// is why the table gives the label its own line at the accessibility sizes
    /// (#10830), and the case the defect cut.
    func testWorldSeriesReallyHasToWrapAtTheLargestSize() throws {
        let oneLine = try drawnSize(tableLabel("World Series"), within: nil, at: .accessibility5)
        XCTAssertGreaterThan(oneLine.width, (Self.seWidth - 32) / 3)
    }

    func testStageLabelsWrapWholeAtTheLargestSizeOnTheNarrowestPhone() throws {
        try assertStageLabelsWhole(width: Self.seWidth, at: .accessibility5)
    }

    func testStageLabelsWrapWholeAtTheLargestSizeOnIPhone17() throws {
        try assertStageLabelsWhole(width: Self.iPhone17Width, at: .accessibility5)
    }

    /// #4395's own photograph: accessibility-large (`.accessibility2`) on a
    /// 375 pt SE. The case the header change alone does NOT cure — with the
    /// name stacked but the label free to be squeezed, both labels still cut
    /// here — so it is the one that holds the label's own fix in place.
    func testStageLabelsWrapWholeAtAccessibilityLargeOnTheNarrowestPhone() throws {
        try assertStageLabelsWhole(width: Self.seWidth, at: .accessibility2)
    }

    // MARK: - The team name

    /// A three-letter code must never split across lines. At the largest size
    /// on the narrowest phone that means it leaves the logo's side.
    func testTheTeamCodeDrawsOnOneLineAtTheLargestSize() throws {
        // The two-team table (#10830); the card's own header is held below.
        let page = try hosted(width: Self.seWidth, at: .accessibility5)
        let cardPage = try hosted(width: Self.seWidth, at: .accessibility5, awayOnly: true)
        let oneLineCHW = try drawnSize(teamName("CHW"), within: nil, at: .accessibility5)
        XCTAssertEqual(cardPage.frames(sized: oneLineCHW).count, 1,
                       "the card's 'CHW' broke mid-word. Text layers: \(describe(cardPage.textFrames))")
        for code in ["CHW", "HOU"] {
            let oneLine = try drawnSize(teamName(code), within: nil, at: .accessibility5)
            XCTAssertEqual(
                page.frames(sized: oneLine).count, 1,
                """
                '\(code)' on one line draws \(oneLine.width)×\(oneLine.height) and no \
                layer that size was drawn — it broke mid-word. Text layers: \
                \(describe(page.textFrames))
                """)
        }
    }

    // MARK: - Control: the default text size keeps the header as it shipped

    /// At the default size the card's name still sits beside its 40 pt logo,
    /// as it always has, rather than under it.
    func testAtTheDefaultSizeTheNameStaysBesideTheLogo() throws {
        let page = try hosted(width: Self.iPhone17Width, at: .large, awayOnly: true)
        let column = Self.cardContentWidth(Self.iPhone17Width)
        let label = try XCTUnwrap(page.frames(
            sized: try drawnSize(stageLabel("Make Playoffs"), within: column, at: .large)).first,
            "Text layers: \(describe(page.textFrames))")
        let name = try XCTUnwrap(page.frames(
            sized: try drawnSize(teamName("CHW"), within: nil, at: .large)).first, "no one-line 'CHW' layer")
        XCTAssertGreaterThanOrEqual(
            name.minX, label.minX + 40, "at the default size 'CHW' must sit right of its logo, not under it")
        XCTAssertLessThan(name.minY, label.minY, "'CHW' belongs to the header above its card's first stage")
    }

    /// #10830 — and the two-team page is ONE aligned table at the default
    /// size: both names on one header row, away left of home, and every stage
    /// label in the left column beneath them.
    func testAtTheDefaultSizeTwoTeamsReadAsOneAlignedTable() throws {
        let page = try hosted(width: Self.iPhone17Width, at: .large)
        let away = try XCTUnwrap(page.frames(
            sized: try drawnSize(teamName("CHW"), within: nil, at: .large)).first, "no 'CHW' header")
        let home = try XCTUnwrap(page.frames(
            sized: try drawnSize(teamName("HOU"), within: nil, at: .large)).first, "no 'HOU' header")
        XCTAssertEqual(away.minY, home.minY, accuracy: 2, "the two names share one header row")
        XCTAssertLessThan(away.maxX, home.minX, "away is the left column, home the right")
        for label in ["Make Playoffs", "Division", "World Series"] {
            let one = try drawnSize(tableLabel(label), within: nil, at: .large)
            let frame = try XCTUnwrap(page.frames(sized: one).first,
                                      "'\(label)' is not drawn whole on one line: \(describe(page.textFrames))")
            XCTAssertLessThan(frame.maxX, away.minX, "'\(label)' sits in the label column")
            XCTAssertGreaterThan(frame.minY, away.maxY, "'\(label)' sits beneath the header row")
        }
        // Each stage appears once — not once per team, as the two cards drew it.
        XCTAssertEqual(page.frames(sized: try drawnSize(tableLabel("Division"), within: nil, at: .large)).count, 1)
    }
}
