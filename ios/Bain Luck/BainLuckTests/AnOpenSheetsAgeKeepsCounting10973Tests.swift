import XCTest
@testable import Bain_Luck

/// #10973 — AN OPEN LIVE PROP SHEET SAID "Updated 4m ago" FOR TWENTY MINUTES.
///
/// Build 50 source, sim 13CB646D, MNF BUF@LAR (14780558): Blake Corum · 1+
/// reception was opened at 02:06Z and held without refreshing. All twelve
/// frames through 02:28Z read "Kalshi · Updated 4m ago"
/// (`artifacts/native-9483/build50-live/hold/live-*.png`). The leg had left
/// `/game-markets`, the held row never changed again, and both sheets formatted
/// the age with `SourceAge.format(observedAt)`, whose `now` defaults to `Date()`
/// at render. That is #7019's freeze, so the fix is #7019's: the age view
/// observes `MinuteClock` and draws against `clock.now`.
///
/// A test of the formatter alone cannot see the freeze (it answers correctly
/// for any instant it is asked about), so the subscription is pinned by a source
/// scan, as `ACountdownChipKeepsAgeing7019Tests` does for `StatusBadge`.
final class AnOpenSheetsAgeKeepsCounting10973Tests: XCTestCase {

    /// An arbitrary fixed instant: nothing here reads a wall clock (gotcha #44).
    private let opened = Date(timeIntervalSince1970: 1_791_684_360)

    /// The stamp the sheet held, 4m30s before the sheet opened.
    private var stamp: String {
        ISO8601DateFormatter().string(from: opened.addingTimeInterval(-270))
    }

    /// ⭐ THE DEFECT AS A PAIR: one stamp, two instants, two strings. The frozen
    /// sheet showed the first at the time of the second.
    func testOneStampReadsDifferentlyTwentyTwoMinutesLater() {
        XCTAssertEqual(SourceAge.format(stamp, now: opened), "4m ago")
        XCTAssertEqual(SourceAge.format(stamp, now: opened.addingTimeInterval(22 * 60)), "26m ago")
    }

    /// A minute is enough to move it, so a 60-second clock is the right tick.
    func testAMinuteMovesTheString() {
        XCTAssertNotEqual(
            SourceAge.format(stamp, now: opened),
            SourceAge.format(stamp, now: opened.addingTimeInterval(60))
        )
    }

    // MARK: - Source scans

    /// Comments stripped and whitespace removed, so the prose beside a line
    /// can never satisfy the scan for it.
    private func code(_ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent(file)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private static let sheets = ["EventPropsMatrixView.swift", "EventQuestionMatrixSection10238.swift"]

    func testTheAgeViewSubscribesToTheClockAndDrawsAgainstIt() throws {
        let view = try code("SourceAgeText.swift")
        XCTAssertTrue(view.contains("structSourceAgeText:View{"), "the scan is not reading SourceAgeText.swift")
        XCTAssertTrue(
            view.contains("@ObservedObjectvarclock=MinuteClock.shared"),
            "SourceAgeText no longer observes MinuteClock, so nothing redraws a held age"
        )
        XCTAssertTrue(
            view.contains("SourceAge.format(observedAt,now:clock.now)"),
            "the age is formatted without the observed instant. The default `now` compiles and freezes"
        )
    }

    /// Every age in both sheets goes through the ticking view. A bare
    /// `SourceAge.format(` left in either file is a frozen age.
    func testBothSheetsDrawEveryAgeThroughTheTickingView() throws {
        for file in Self.sheets {
            let source = try code(file)
            XCTAssertTrue(source.contains("SourceAgeText(observedAt:"), "\(file) no longer draws a SourceAgeText")
            XCTAssertTrue(source.contains("prefix:\"Updated\""), "\(file) lost its \"Updated …\" summary line")
            XCTAssertFalse(source.contains("SourceAge.format("), "\(file) formats an age that never ticks")
        }
    }
}
