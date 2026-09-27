import XCTest
@testable import Bain_Luck

/// #8320 — A LIVE EVENT PAGE SAID HOW FRESH IT WAS THREE TIMES.
///
/// Alex, rage shake #150, White Sox–Royals (15317520), 2026-09-23 6:06 PM PDT
/// (`artifacts/event-page-feedback-20260924/user-screen-2.png`): "This whole
/// area at the top of the screen is overcrowded and clowny looking." On one
/// screen:
///
///     toolbar           [●]                 ← refresh ring / push dot
///     hero              [● Bottom 4th]      ← the game state
///     chart title       Win Probability ● Live      [●]  ⤢
///                                       ↑ second dot  ↑ second ring
///
/// The toolbar ring and the chart-title ring were the same control drawn twice
/// (`refreshRing` / `refreshCountdownRing`, both `LivePushDot` while pushed and
/// a 30-second countdown otherwise), and the chart's "● Live" repeated the
/// hero's chip. A countdown to the next poll is plumbing, not something a fan
/// reads (Codex brief: "No countdown in default reader UI").
///
/// After: the toolbar carries the page's ONE status — the push dot while the
/// stream delivers, a plain refresh glyph while polled — and the chart title
/// carries none. Fullscreen covers the toolbar, so it repeats the push dot and
/// nothing else.
///
/// These are source scans because the routing lives in `View` bodies no test
/// can instantiate headlessly; comments are stripped first so this fix's own
/// prose cannot satisfy a claim about the code it sits beside
/// (`HeroSaysTheCountdownOnce6544Tests` is the model).
final class ALiveEventPageSaysItsFreshnessOnce8320Tests: XCTestCase {

    private func code(_ directory: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(directory)
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

    private func pageCode() throws -> String { try code("Views", "EventDetailView.swift") }
    private func chartCode() throws -> String { try code("Components", "OddsChartView.swift") }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    /// Anti-vacuity: if these fail, every scan below is about the wrong file.
    func testTheScansCanSeeTheFilesTheyAreAbout() throws {
        XCTAssertTrue(try code("Views", "EventDetailView.swift").contains("structEventDetailView:View{"))
        XCTAssertTrue(try chartCode().contains("structOddsChartView:View{"))
    }

    // MARK: - No countdown on the page

    func testNeitherFileCountsDownToAPoll() throws {
        for (name, source) in [("EventDetailView", try code("Views", "EventDetailView.swift")), ("OddsChartView", try chartCode())] {
            XCTAssertFalse(source.contains("refreshCountdown"),
                           "\(name) is carrying a refresh countdown again (#8320)")
            XCTAssertFalse(source.contains("\"Nextupdate"),
                           "\(name) prints \"Next update\" — a poll countdown on a reader's screen")
            XCTAssertFalse(source.contains("refreshRemaining("),
                           "\(name) computes seconds-to-next-poll, which only a countdown reads")
        }
    }

    /// The half-second timer existed only to move the countdown. A page that
    /// re-renders twice a second while nothing changed is manufacturing ticks
    /// (the brief: "never manufacture animation/ticks while unchanged").
    func testThePageRunsNoHalfSecondTimer() throws {
        XCTAssertFalse(try code("Views", "EventDetailView.swift").contains("Timer.scheduledTimer(withTimeInterval:0.5"))
    }

    // MARK: - One status, in the toolbar

    func testReadableStatusAndManualRefreshAreSeparate() throws {
        let page = try code("Views", "EventDetailView.swift")
        XCTAssertEqual(occurrences(of: "LiveUpdateStatusView(status:vm.liveUpdateStatus)", in: page), 2)
        XCTAssertTrue(page.contains(".accessibilityLabel(\"Refreshnow\")"))
        XCTAssertTrue(page.contains("Button{Task{awaitvm.load()}}label:{Image(systemName:\"arrow.clockwise\")"))
        XCTAssertEqual(occurrences(of: "LivePushDot(", in: page), 0)
    }

    func testOnlyProvenDeliveryGetsAGreenMarker() throws {
        let status = try code("Components", "LiveUpdateStatusView.swift")
        XCTAssertTrue(status.contains("ifstatus==.live{Circle().fill(.green)"))
        XCTAssertFalse(status.contains("Timer"))
        XCTAssertFalse(status.contains("repeatForever"))
    }

    // MARK: - The chart title carries none of it

    func testTheChartTitleHasNoLiveChipAndNoRing() throws {
        let chart = try chartCode()
        XCTAssertFalse(chart.contains("Text(\"Live\")"),
                       "the chart title is repeating the hero's live chip (#8320)")
        guard let trailing = chart.range(of: "privatevarchartHeaderTrailingControls:someView{") else {
            return XCTFail("chartHeaderTrailingControls moved; re-aim this scan")
        }
        let body = String(chart[trailing.upperBound...].prefix(300))
        XCTAssertFalse(body.contains("LivePushDot"), body)
        XCTAssertTrue(body.contains("isFullscreen=true"), "control: the scan is reading the trailing controls")
    }

    /// ⭐ THE OMISSION A BAN CANNOT SEE: fullscreen hides the page toolbar, so a
    /// chart scan that only bans things would pass on a fullscreen view that
    /// silently lost the status. Pin the one it keeps, and that it is gated on
    /// a delivering stream.
    func testFullscreenKeepsTheSameReadableStatusAsThePage() throws {
        let chart = try chartCode()
        XCTAssertEqual(occurrences(of: "LivePushDot(", in: chart), 0)
        XCTAssertTrue(chart.contains("ifstatus==\"live\"&&liveUpdateStatus != .hidden{".replacingOccurrences(of: " ", with: "")
                                     + "ToolbarItem(placement:.cancellationAction){LiveUpdateStatusView(status:liveUpdateStatus)}}"))
        XCTAssertTrue(try code("Views", "EventDetailView.swift").contains("liveUpdateStatus:vm.liveUpdateStatus"))
    }

    /// The Final chip is a settled-state label, not a freshness claim, and
    /// #8320 did not ask for it to go ("settled means settled").
    func testTheFinalChipSurvives() throws {
        XCTAssertTrue(try chartCode().contains("Text(\"Final\")"))
    }
}
