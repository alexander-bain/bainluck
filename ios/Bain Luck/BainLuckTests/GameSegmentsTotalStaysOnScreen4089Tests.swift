import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #4089 — at the accessibility text sizes the Game Segments table ran past the
/// right edge of the phone and took the `T` column with it, because the one
/// horizontal scroll view held the whole row.
///
/// The claim is about where the scroll view ENDS, so this hosts the shipped
/// `GameSegmentsTable` in a window at a phone's card width and reads the frame of
/// the scroll view UIKit actually built. Pinned, it stops short of the right edge
/// by at least the width of the total column (measured separately, at the same
/// text size); unpinned, it spans the full width and the total is inside it.
///
/// `ViewThatFits` picks its arm during layout, so an unhosted `sizeThatFits` would
/// be measuring a decision that has not been taken yet — hence the window
/// (the same rig as `TheEvolutionCardFitsTheScreenAtEveryTypeSize4445Tests`).
@MainActor
final class GameSegmentsTotalStaysOnScreen4089Tests: XCTestCase {

    /// Card content widths: the screen minus the page's 16pt margin and the
    /// card's 16pt padding, each side (`EventDetailView`'s `.padding(.horizontal)`
    /// around the stack, `.padding()` on the card). 375pt SE — the narrowest
    /// supported phone — and 402pt iPhone 17, #4089's.
    private static let seContent: CGFloat = 375 - 64
    private static let iPhone17Content: CGFloat = 402 - 64

    private static let epsilon: CGFloat = 0.5

    /// Athletics 6 – Mariners 2 (`15304933`), the page #4089 was photographed on.
    private static func nineInnings() -> [LineScoreColumn] {
        let away = [0, 1, 0, 2, 0, 0, 3, 0, 0]
        let home = [0, 0, 1, 0, 0, 1, 0, 0, 0]
        return (0..<9).map {
            LineScoreColumn(label: String($0 + 1), away: .score(away[$0]), home: .score(home[$0]))
        }
    }

    private static func table(_ columns: [LineScoreColumn]) -> GameSegmentsTable {
        GameSegmentsTable(
            columns: columns,
            awayBadge: "ATH", homeBadge: "SEA",
            awayColor: .green, homeColor: .teal,
            awayTotal: 6, homeTotal: 2)
    }

    private struct Hosted {
        let host: UIViewController
        let window: UIWindow
        var scrollViews: [UIScrollView] {
            var found: [UIScrollView] = []
            func walk(_ view: UIView) {
                if let scroll = view as? UIScrollView { found.append(scroll) }
                view.subviews.forEach(walk)
            }
            walk(host.view)
            return found
        }
    }

    private func hosted<V: View>(_ view: V, width: CGFloat, at size: DynamicTypeSize) -> Hosted {
        let host = hostForMeasurement(
            view.frame(width: width, alignment: .leading)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading),
            at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 600))
        window.rootViewController = host
        window.isHidden = false
        host.view.frame = window.bounds
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return Hosted(host: host, window: window)
    }

    /// The width the total column draws at a text size: the wider of the header
    /// `T` and the two-row total, each with its 6pt gutter, plus the 4pt gap that
    /// separates it from the periods.
    private func totalColumnWidth(at size: DynamicTypeSize) throws -> CGFloat {
        func width<V: View>(_ view: V) throws -> CGFloat {
            let renderer = rendererForMeasurement(view, at: size)
            // @3x, so the raster rounds to a third of a point, as the screen does.
            renderer.scale = 3
            return try XCTUnwrap(renderer.uiImage).size.width
        }
        let header = try width(
            Text("T").font(.caption2.weight(.bold)).frame(minWidth: 26).padding(.leading, 6))
        let total = try width(
            Text("6").font(.caption.weight(.bold).monospacedDigit())
                .frame(minWidth: 26).padding(.leading, 6))
        return max(header, total) + GameSegmentsTable.columnSpacing
    }

    // MARK: - Control: the default text size keeps UX-P090's single table

    func testANineInningGameAtTheDefaultSizeIsOneTableThatDoesNotScroll() {
        let page = hosted(Self.table(Self.nineInnings()), width: Self.iPhone17Content, at: .large)
        XCTAssertTrue(
            page.scrollViews.isEmpty,
            """
            a nine-inning table fits a 402pt iPhone at the default size, so it must \
            draw as the one table UX-P090 shipped, with nothing to scroll — got \
            \(page.scrollViews.count) scroll view(s)
            """)
    }

    /// The pinned layout is three grids side by side; if one resolves a taller
    /// row than the others, the team names, innings and totals shear apart. So
    /// the three must draw at the same height at every size the layout is used.
    func testThePinnedGridsKeepTheirRowsLevel() throws {
        for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3, .accessibility5] {
            let heights = try [GameSegmentsTable.Part.teams, .periods, .totals].map { part in
                let renderer = rendererForMeasurement(
                    Self.table(Self.nineInnings()).grid(part), at: size)
                renderer.scale = 3
                return try XCTUnwrap(renderer.uiImage).size.height
            }
            XCTAssertEqual(heights[0], heights[1], accuracy: Self.epsilon, "teams vs periods @ \(size)")
            XCTAssertEqual(heights[2], heights[1], accuracy: Self.epsilon, "totals vs periods @ \(size)")
        }
    }

    // MARK: - The defect: the accessibility sizes

    private func assertTotalsPinned(
        width: CGFloat, at size: DynamicTypeSize,
        file: StaticString = #filePath, line: UInt = #line
    ) throws {
        let page = hosted(Self.table(Self.nineInnings()), width: width, at: size)
        let scroll = try XCTUnwrap(
            page.scrollViews.first,
            "at \(size) on \(width)pt the table overflows, so the periods must scroll",
            file: file, line: line)
        XCTAssertEqual(page.scrollViews.count, 1, file: file, line: line)

        let frame = scroll.convert(scroll.bounds, to: page.host.view)
        // Not vacuous: the innings really do overflow, so which column the scroll
        // view holds decides what the reader loses.
        XCTAssertGreaterThan(
            scroll.contentSize.width, frame.width + Self.epsilon,
            "at \(size) the innings should not fit \(frame.width)pt — the case is vacuous",
            file: file, line: line)

        let totals = try totalColumnWidth(at: size)
        XCTAssertLessThanOrEqual(
            frame.maxX, width - totals + Self.epsilon,
            """
            at \(size) on \(width)pt the scroll view ends at \(frame.maxX)pt, leaving \
            \(width - frame.maxX)pt — the total column needs \(totals)pt, so `T` is \
            inside the scroll view and off screen
            """,
            file: file, line: line)
        XCTAssertGreaterThanOrEqual(
            frame.minX, GameSegmentTeamBadge.minimumWidthPoints,
            "the team names must stay pinned to the left of the scrolling periods",
            file: file, line: line)
    }

    /// #4089's own photograph: accessibility-extra-large on a 402pt iPhone 17.
    func testTheTotalsStayOnScreenAtAccessibilityExtraLarge() throws {
        try assertTotalsPinned(width: Self.iPhone17Content, at: .accessibility3)
    }

    /// The largest size on the narrowest phone.
    func testTheTotalsStayOnScreenAtTheLargestSizeOnTheNarrowestPhone() throws {
        try assertTotalsPinned(width: Self.seContent, at: .accessibility5)
    }

    /// Extras at the default size — the other way the row overflows.
    func testAnExtraInningsGameAtTheDefaultSizeKeepsItsTotalsOnScreen() throws {
        var columns = Self.nineInnings()
        for inning in 10...13 {
            columns.append(LineScoreColumn(label: String(inning), away: .score(0), home: .score(0)))
        }
        let page = hosted(Self.table(columns), width: Self.seContent, at: .large)
        let scroll = try XCTUnwrap(page.scrollViews.first, "13 innings overflow a 375pt SE")
        let frame = scroll.convert(scroll.bounds, to: page.host.view)
        XCTAssertLessThanOrEqual(
            frame.maxX, Self.seContent - (try totalColumnWidth(at: .large)) + Self.epsilon)
    }
}
