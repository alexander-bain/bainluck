import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9392 — a totals rung the venue is still trading at 99.55% reads `>99%`, the
/// way the hero above it does, and it reads on ONE line.
///
/// THE PHOTOGRAPH: `artifacts/native-walk-1425Z/soccer-s900.png`, iPhone 17
/// against production, master `91183e5bf7`, 2026-09-28 14:31Z. Event 15317879,
/// Maldives @ Kyrgyz Republic, live, hero `Kyrgyz Republic >99%`:
///
/// ```
/// Goals map                 Over 0.5 100% · Over 1.5 100% · Over 2.5 100%
/// Projected combined goals  0.5+  ▬▬▬▬▬▬▬▬  100
///                                          %
/// ```
///
/// Served `over_probability`: 0.9995 on the 0.5 line, 0.9955 on 1.5 / 2.5 / 3.5.
/// Both ladders interpolated `Int((p * 100).rounded())` instead of going through
/// `formatProbability`, and the spectrum's value column was a bare 32 pt with
/// no `lineLimit` that `100%` does not fit at 11 pt.
final class TotalsRungPrintsTheHerosClamp9392Tests: XCTestCase {

    // MARK: - The ship

    /// 🟢 The specimen's own served prices print the hero's words.
    func testTheSpecimensStillTradingLinesReadAsTheHeroDoes() {
        XCTAssertEqual(MarketMapRail.rungPercentText(0.9995), ">99%", "the 0.5 line")
        XCTAssertEqual(MarketMapRail.rungPercentText(0.9955), ">99%", "the 1.5 / 2.5 / 3.5 lines")
        XCTAssertEqual(MarketMapRail.rungPercentText(0.29), "29%", "the 4.5 line is unchanged")
        XCTAssertEqual(MarketMapRail.rungPercentText(0.004), "<1%")
    }

    /// The rung and the hero cannot drift: the rung's words ARE the app-wide
    /// rule, asked of a sweep of prices, not a restatement of it.
    func testTheRungSaysExactlyWhatFormatProbabilitySays() {
        for basisPoints in stride(from: 0, through: 10_000, by: 5) {
            let p = Double(basisPoints) / 10_000
            XCTAssertEqual(MarketMapRail.rungPercentText(p), formatProbability(p), "at \(p)")
        }
    }

    // MARK: - The column

    /// 🔴 The number fits its column on one line, measured in the font the card
    /// draws — every shape `rungPercentText` can return, at its widest digits.
    @MainActor
    func testThePercentColumnHoldsEveryRungNumber() {
        var widest: (text: String, width: CGFloat) = ("", 0)
        for text in [">99%", "<1%", "99%", "88%", "100%", "0%"] {
            let wanted = naturalWidth(of: percentText(text))
            if wanted > widest.width { widest = (text, wanted) }
        }
        XCTAssertGreaterThanOrEqual(
            TotalPointsSpectrumView.percentColumnWidth, widest.width,
            "'\(widest.text)' wants \(widest.width) pt against the "
            + "\(TotalPointsSpectrumView.percentColumnWidth) pt column")
    }

    /// The premise: the OLD 32 pt column really could not hold these, which is
    /// why the specimen wrapped. If this ever fails the font changed, and the
    /// column above should be re-measured rather than trusted.
    @MainActor
    func testTheOldThirtyTwoPointColumnCouldNotHoldTheNumber() {
        XCTAssertGreaterThan(naturalWidth(of: percentText("100%")), 32)
        XCTAssertGreaterThan(naturalWidth(of: percentText(">99%")), 32)
    }

    // MARK: - The call sites

    /// Both ladders' views are private SwiftUI, so the fact is read from the
    /// FILES: each ungraded rung routes through `rungPercentText`, and neither
    /// file builds a percent by hand any more.
    func testNeitherLadderBuildsItsPercentByHand() throws {
        for file in ["Bain Luck/Components/MarketMapView.swift",
                     "Bain Luck/Components/TotalPointsSpectrumView.swift"] {
            let source = try String(
                contentsOf: Self.projectDirectory.appendingPathComponent(file), encoding: .utf8)
            XCTAssertTrue(source.contains("MarketMapRail.rungPercentText("),
                          "\(file) no longer routes its rung through the shared clamp")
            XCTAssertFalse(source.contains("* 100).rounded()))%\")"),
                           "\(file) builds a percent inline again — that is #9392's `100%`")
        }
    }

    /// The spectrum's rung is one line in the measured column.
    func testTheSpectrumRungIsOneLineInTheMeasuredColumn() throws {
        let source = try String(
            contentsOf: Self.projectDirectory
                .appendingPathComponent("Bain Luck/Components/TotalPointsSpectrumView.swift"),
            encoding: .utf8)
        let call = try XCTUnwrap(source.range(of: "Text(MarketMapRail.rungPercentText(prob))"))
        let tail = String(source[call.upperBound...].prefix(260))
        XCTAssertTrue(tail.contains(".font(Self.percentFont)"), tail)
        XCTAssertTrue(tail.contains(".lineLimit(1)"), tail)
        XCTAssertTrue(tail.contains(".frame(width: Self.percentColumnWidth"), tail)
    }

    // MARK: - Helpers

    private func percentText(_ text: String) -> some View {
        Text(text).font(TotalPointsSpectrumView.percentFont).lineLimit(1)
    }

    @MainActor
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = hostForMeasurement(view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }

    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
