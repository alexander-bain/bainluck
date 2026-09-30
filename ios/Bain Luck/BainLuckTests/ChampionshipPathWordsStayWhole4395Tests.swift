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
    private static func progression() throws -> TeamProgressionResponse {
        let json = #"""
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

    private func hosted(width: CGFloat, at size: DynamicTypeSize) throws -> Hosted {
        let view = ChampionshipPathView(progression: try Self.progression())
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

    /// The width a card gives its rows: the view's own 16 pt padding each side,
    /// then `ChampionshipRowLayout`'s split between two cards.
    private static func cardContentWidth(_ width: CGFloat) -> CGFloat {
        ChampionshipRowLayout.teamCardContentWidth(totalWidth: width - 32, cardCount: 2)
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
        let page = try hosted(width: width, at: size)
        let column = Self.cardContentWidth(width)
        for label in ["Make Playoffs", "World Series"] {
            let whole = try drawnSize(stageLabel(label), within: column, at: size)
            let found = page.frames(sized: whole)
            XCTAssertEqual(
                found.count, 2,
                """
                at \(size) on \(width)pt '\(label)' wrapped whole in a \(column)pt card \
                draws \(whole.width)×\(whole.height); expected one such layer per card, \
                found \(found.count). Text layers: \(describe(page.textFrames))
                """,
                file: file, line: line)
        }
    }

    /// Not vacuous: at this size "World Series" cannot sit on one line in a
    /// card, so the label must wrap — the case the defect cut.
    func testWorldSeriesReallyHasToWrapAtTheLargestSize() throws {
        let oneLine = try drawnSize(stageLabel("World Series"), within: nil, at: .accessibility5)
        XCTAssertGreaterThan(oneLine.width, Self.cardContentWidth(Self.seWidth))
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
        let page = try hosted(width: Self.seWidth, at: .accessibility5)
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

    /// At the default size the name still sits beside its 40 pt logo, as it
    /// always has, rather than under it.
    func testAtTheDefaultSizeTheNameStaysBesideTheLogo() throws {
        let page = try hosted(width: Self.iPhone17Width, at: .large)
        let column = Self.cardContentWidth(Self.iPhone17Width)
        let labels = page.frames(
            sized: try drawnSize(stageLabel("Make Playoffs"), within: column, at: .large))
            .sorted { $0.minX < $1.minX }
        XCTAssertEqual(labels.count, 2, "Text layers: \(describe(page.textFrames))")
        for (code, label) in zip(["CHW", "HOU"], labels) {
            let names = page.frames(
                sized: try drawnSize(teamName(code), within: nil, at: .large))
            let name = try XCTUnwrap(names.first, "no one-line '\(code)' layer")
            XCTAssertGreaterThanOrEqual(
                name.minX, label.minX + 40,
                "at the default size '\(code)' must sit right of its logo, not under it")
            XCTAssertLessThan(
                name.minY, label.minY,
                "'\(code)' belongs to the header above its card's first stage")
        }
    }
}
