import XCTest
@testable import Bain_Luck

/// #10090 / #11105 — Alex's build-93 chart tail (event 15334769, 2026-10-30
/// 20:22–20:24Z): the line ran flat at 41.6%, met the 40.6% dot, then stopped
/// short of it. The read's 20:22:00 bucket already held the 40.643% move and
/// was drawn at its minute's start, before the 41.618% frame pushed at
/// 20:22:15: an out-and-back the headline never showed. Values from native's
/// b94-findings return §3 and the b93 hold's liveTiming marks:
///   frames  rev 1852 20:21:41.582 0.41618 · rev 1853 20:22:15.456 0.41618 ·
///           rev 1855 20:22:35.460 0.40643
///   buckets 20:20:00 0.41618 · 20:21:00 0.41618 · 20:22:00 0.40643 (public
///           /history read 2026-10-30 ~22:05Z)
///   headline rev 1854 0.40643 observed 20:22:15.456 (the read at 20:22:33.0);
///           rev 1855 0.40643 observed 20:22:35.460; previews b1855 0.40643 at
///           20:22:43.423.
/// The phone's own history payload was not captured, so the pin (time, value,
/// observed, revision) is a parameter of each case. The tail ran mostly under a
/// displayed preview (S2), where the bucket meets the held frame that printed
/// its value (`servedBlendAtEvidenceTime`).
@MainActor
final class TheBuild93TailCrossesTheHeadlineOnce10090Tests: XCTestCase {
    private static let id = 1
    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static func ts(_ hms: String) -> String { "2026-10-30T\(hms)+00:00" }
    private static func date(_ hms: String) -> Date { ts(hms).asDate! }

    private static let f1852 = LiveBlendPoint(date: date("20:21:41.582000"), homeProbability: 0.41618)
    private static let f1853 = LiveBlendPoint(date: date("20:22:15.456000"), homeProbability: 0.41618)
    private static let f1855 = LiveBlendPoint(date: date("20:22:35.460000"), homeProbability: 0.40643)

    private static func event(rev: Int, observed: String) throws -> EventDetail {
        try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: [
            "id": id, "home_team": "Home", "away_team": "Away", "sport": "tennis_atp", "status": "live",
            "current_odds": ["home_probability": 0.40643, "away_probability": 0.59357],
            "hero_probability": 0.40643, "hero_probability_away": 0.59357, "hero_probability_source": "blend",
            "hero_probability_observed_at": ts(observed), "blend_fold_revision": ["1": rev, "2": 5]] as [String: Any]))
    }

    /// The read: three buckets, then the pin at `readAt`. Kalshi's 20:22:20
    /// reading makes 20:22:00 a REAL minute (it moved the blend to 40.643%).
    private static func read(readAt: String, pin: Double, observed: String, rev: Int) throws -> EventHistoryResponse {
        let sources: [String: [[String: Any]]] = [
            "kalshi": [["timestamp": ts("20:18:00"), "home_probability": 0.415],
                       ["timestamp": ts("20:22:20"), "home_probability": 0.405],
                       ["timestamp": ts(readAt), "home_probability": 0.405, "live_edge": true]],
            "polymarket": [["timestamp": ts("20:18:29"), "home_probability": 0.435],
                           ["timestamp": ts(readAt), "home_probability": 0.435, "live_edge": true]],
        ]
        let line: [(String, Double)] = [(ts("20:20:00"), 0.41618), (ts("20:21:00"), 0.41618),
                                        (ts("20:22:00"), 0.40643), (ts(readAt), pin)]
        let payload: [String: Any] = [
            "event_id": id, "home_team": "Home", "away_team": "Away", "status": "live", "history": [],
            "aggregate_line": line.map { ["timestamp": $0.0, "home_probability": $0.1] },
            "blend_edge_pinned": true, "blend_edge_observed_at": ts(observed),
            "blend_edge_fold_revision": ["1": rev, "2": 5], "win_prob_history": sources]
        return try decoder.decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    /// Preview b1855 as the page holds it: 40.643% (= committed), observed 20:22:43.423.
    private static func preview(baseRev: Int) throws -> BlendPreviewState? {
        let raw = String(data: try JSONSerialization.data(withJSONObject: [
            "event_id": id, "p": 0.40643, "p_away": 0.59357, "sport": "tennis_atp", "status": "live",
            "display_observed_at": ts("20:22:43.423000"),
            "preview": ["kind": "blend", "epoch": 3, "seq": 5, "base_rev": baseRev, "ttl_ms": 60_000,
                        "folded_version": 1, "origin_event_id": id, "base_fold_revision": ["1": baseRev, "2": 5],
                        "pending_entries_version": 2, "pending_entries_authority": "event-ledger-v1"],
        ] as [String: Any]), encoding: .utf8)!
        return BlendPreview.readerAfter(.empty, try XCTUnwrap(BlendPreviewFrame.decode(raw)), eventId: id, now: 0.116).held
    }

    private static func drawn(_ served: EventHistoryResponse, _ event: EventDetail, _ state: BlendPreviewState?,
                              pushed: [LiveBlendPoint]) -> [ChartDataPoint] {
        let frames = BlendPreview.chartFrames(pushed, history: served, state: state, held: event, now: 1.0)
        return OddsChartView.chartPoints(from: served, liveFrames: frames)
            .filter { $0.source == "aggregate" }
            .sorted { $0.date < $1.date }
    }

    private static func text(_ points: [ChartDataPoint]) -> String {
        points.map { String(format: "%.3f=%.5f", $0.date.timeIntervalSince(date("20:22:00")), $0.probability) }
            .joined(separator: "  ")
    }

    /// The tail moved 41.618% → 40.643% once. Drawn time-ordered, the values
    /// must change once: never back up to 41.618% after showing 40.643%.
    private static func assertOneCrossing(_ points: [ChartDataPoint], _ name: String,
                                          file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(points.last?.probability, 0.40643, "\(name): ends on the headline", file: file, line: line)
        guard let first = points.firstIndex(where: { $0.probability == 0.40643 }) else {
            return XCTFail("\(name): never shows the headline", file: file, line: line)
        }
        let back = points[first...].filter { $0.probability != 0.40643 }
        XCTAssertTrue(back.isEmpty, "\(name): out-and-back — \(text(Array(points[first...])))", file: file, line: line)
    }

    // MARK: - S1: committed windows (no preview) — R1's class

    /// Native's reading of the tail: the read's 20:22:00 bucket already holds
    /// the 40.643% commit and the read's pin still carries an older 41.618%.
    /// Headline rev 1855 at its frame's clock 20:22:35.460, pin at 20:22:50.
    func testS1aCommittedHeadlineOverAnOlderPinAfterTheCommitFrame() throws {
        let served = try Self.read(readAt: "20:22:50", pin: 0.41618, observed: "20:22:15.456000", rev: 2)
        let event = try Self.event(rev: 3, observed: "20:22:35.460000")
        Self.assertOneCrossing(Self.drawn(served, event, nil, pushed: [Self.f1852, Self.f1853, Self.f1855]), "S1a")
    }

    /// 20:22:33.0–20:22:35.37: headline rev 1854 from the read, observed
    /// 20:22:15.456 — the SAME clock as the pushed 41.618% frame rev 1853.
    func testS1bHeadlineClockEqualsAPushedFrameWithTheOlderValue() throws {
        let served = try Self.read(readAt: "20:22:30.600000", pin: 0.41618, observed: "20:21:41.582000", rev: 2)
        let event = try Self.event(rev: 3, observed: "20:22:15.456000")
        Self.assertOneCrossing(Self.drawn(served, event, nil, pushed: [Self.f1852, Self.f1853]), "S1b")
    }

    /// A pin already printing the headline: no marker, the generic rule.
    func testS1cPinAlreadyPrintsTheHeadline() throws {
        let served = try Self.read(readAt: "20:22:50", pin: 0.40643, observed: "20:22:35.460000", rev: 3)
        let event = try Self.event(rev: 3, observed: "20:22:35.460000")
        Self.assertOneCrossing(Self.drawn(served, event, nil, pushed: [Self.f1852, Self.f1853, Self.f1855]), "S1c")
    }

    // MARK: - S2: preview windows (b1855 displayed) — the #11755 relabel

    /// The preview replaces a pin read at/after its observation (20:22:50):
    /// `previewAt` caps the relabel, and the 20:22:00 bucket meets frame rev
    /// 1855 (20:22:35.460) instead of staying at its minute's start.
    func testS2aPreviewReplacesThePinAndTheBucketMeetsItsFrame() throws {
        let served = try Self.read(readAt: "20:22:50", pin: 0.40643, observed: "20:22:15.456000", rev: 3)
        let event = try Self.event(rev: 3, observed: "20:22:35.460000")
        let state = try Self.preview(baseRev: 3)
        XCTAssertNotNil(BlendPreview.displayed(state, held: event, now: 1.0), "the preview is displayed")
        Self.assertOneCrossing(Self.drawn(served, event, state, pushed: [Self.f1852, Self.f1853, Self.f1855]), "S2a")
    }

    /// The same with the stale 41.618% pin.
    func testS2bPreviewReplacesAStalePin() throws {
        let served = try Self.read(readAt: "20:22:50", pin: 0.41618, observed: "20:22:15.456000", rev: 2)
        let event = try Self.event(rev: 3, observed: "20:22:35.460000")
        let state = try Self.preview(baseRev: 3)
        Self.assertOneCrossing(Self.drawn(served, event, state, pushed: [Self.f1852, Self.f1853, Self.f1855]), "S2b")
    }

    /// A pin read BEFORE the preview's observation is not replaced: generic rule.
    func testS2cPreviewAfterThePin() throws {
        let served = try Self.read(readAt: "20:22:30.600000", pin: 0.40643, observed: "20:22:15.456000", rev: 3)
        let event = try Self.event(rev: 3, observed: "20:22:35.460000")
        let state = try Self.preview(baseRev: 3)
        Self.assertOneCrossing(Self.drawn(served, event, state, pushed: [Self.f1852, Self.f1853, Self.f1855]), "S2c")
    }
}
