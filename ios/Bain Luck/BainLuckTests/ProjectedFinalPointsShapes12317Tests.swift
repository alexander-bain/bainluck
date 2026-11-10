import XCTest
@testable import Bain_Luck

/// #12317 (Differentiate Without Color) — the "Projected final points" chart's
/// two lines can be told apart without colour: home circles, away diamonds, and
/// the key above the chart shows each team's shape beside its name.
final class ProjectedFinalPointsShapes12317Tests: XCTestCase {

    func testTheKeyShowsHomeCirclesAndAwayDiamonds() {
        XCTAssertEqual(ProjectedFinalPointsChartView.keyGlyph(home: true), "circle.fill")
        XCTAssertEqual(ProjectedFinalPointsChartView.keyGlyph(home: false), "diamond.fill")
    }

    func testTheKeyAndThePlotAgreeOnWhichShapeIsWhichTeam() throws {
        let source = try Self.squashedSource()
        // The plot: side 0 is home, drawn with circles.
        XCTAssertTrue(source.contains("letvalue=side==0?point.home:point.away"))
        XCTAssertTrue(source.contains(".symbol(side==0?.circle:.diamond)"))
        // The key: the home team's readout carries the home shape, the away team's the away shape.
        XCTAssertTrue(source.contains("teamReadout(homeTeam,forecast:series.latest.home,actual:series.latestActual?.home,color:homeColor,glyph:Self.keyGlyph(home:true))"))
        XCTAssertTrue(source.contains("teamReadout(awayTeam,forecast:series.latest.away,actual:series.latestActual?.away,color:awayColor,glyph:Self.keyGlyph(home:false))"))
        XCTAssertTrue(source.contains("Image(systemName:glyph)"), "the readout draws the shape it is given")
    }

    func testTheNewestPointIsLargeEnoughToReadItsShape() throws {
        let source = try Self.squashedSource()
        XCTAssertTrue(source.contains(".symbolSize(isNewest?80:22)"))
        XCTAssertTrue(source.contains("letisNewest=segment.offset==series.segments.count-1&&entry.offset==segment.element.count-1"))
    }

    private static func squashedSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/ProjectedFinalPointsChartView.swift")
        return try String(contentsOf: url, encoding: .utf8).filter { !$0.isWhitespace }
    }
}
