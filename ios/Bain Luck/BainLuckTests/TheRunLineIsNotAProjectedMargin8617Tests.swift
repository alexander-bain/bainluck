import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8617 — an MLB game's Score Differential stops drawing the run line as a
/// projected margin. The iPhone half of web PR #8621.
///
/// The chart's orange dashed line is the served
/// `projected_home_score - projected_away_score`. The backend solves those two
/// numbers from each sportsbook's spread point and total, so their difference
/// IS the spread point. In baseball that point is the run line — ±1.5 whatever
/// the matchup, the price doing the work — so the line could only read about
/// ±1.5. `/events/15318166` (Mets @ Rangers, priced 55%) served ±1.5 / 2.5 from
/// every sportsbook: "Rangers by 1.5" for a coin flip.
///
/// FIXTURE: `Fixtures/event-15318166-history-8617-run-line.20260925.json`, the
/// served `/history` reduced to shape (see its `_fixture_note`).
///
/// The pair: the same bytes rendered as MLB and as NFL. NFL is the control —
/// it proves the payload carries a projection that draws and that the ink
/// counter can see orange, so a zero under MLB is the gate, not a blind rig.
@MainActor
final class TheRunLineIsNotAProjectedMargin8617Tests: XCTestCase {

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-15318166-history-8617-run-line.20260925.json")
    }

    /// The fixture's own `commence_time` (the response model does not decode it).
    private static let commence = "2026-09-24T18:35:00Z"

    private func specimen(dropScores: Bool = false) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
        if dropScores { object.removeValue(forKey: "score_history") }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private struct Ink { let orange: Int, teal: Int, width: Int }

    private func ink(sportKey: String, dropScores: Bool = false, name: String) throws -> Ink {
        let history = try specimen(dropScores: dropScores)
        let view = ScoreDifferentialChartView(
            history: history, homeTeam: "Texas Rangers", awayTeam: "New York Mets",
            sportKey: sportKey, commenceTime: Self.commence, eventStatus: "completed",
            homeTeamColor: .red, awayTeamColor: .blue,
            homeTeamAbbrev: "TEX", awayTeamAbbrev: "NYM")
            .padding(16)
            .frame(width: 390)
            .background(Color.white)
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        guard let image = renderer.cgImage else { return Ink(orange: 0, teal: 0, width: 0) }

        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("8617-\(name).png")
        try? UIImage(cgImage: image).pngData()?.write(to: url)
        print("8617 render artifact [\(name)]: \(url.path)")

        let w = image.width, h = image.height
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        var orange = 0, teal = 0
        for i in stride(from: 0, to: bytes.count, by: 4) {
            let r = Int(bytes[i]), g = Int(bytes[i + 1]), b = Int(bytes[i + 2])
            // `Color.orange` ≈ (255, 149, 0); the actual line is #0d9488.
            if r > 200, (100...190).contains(g), b < 90 { orange += 1 }
            if r < 70, g > 110, b > 100, g - r > 60 { teal += 1 }
        }
        return Ink(orange: orange, teal: teal, width: w)
    }

    // MARK: - The vocab row

    func testOnlyBaseballSaysItsSpreadIsNotAMargin() {
        XCTAssertFalse(SportVocab.forSport("baseball_mlb").sportsbookSpreadIsAMargin)
        XCTAssertFalse(SportVocab.forSport("baseball_npb").sportsbookSpreadIsAMargin)
        for key in ["americanfootball_nfl", "basketball_nba", "icehockey_nhl",
                    "soccer_epl", "tennis_atp_us_open", "mma_mixed_martial_arts"] {
            XCTAssertTrue(SportVocab.forSport(key).sportsbookSpreadIsAMargin,
                          "\(key) keeps its projection — only the measured sport withholds")
        }
    }

    // MARK: - The pair

    /// The specimen as the phone renders it: the played score (3–1) is drawn,
    /// the ±1.5 run line is not.
    func testTheMLBSpecimenDrawsThePlayedScoreAndNoProjection() throws {
        let mlb = try ink(sportKey: "baseball_mlb", name: "mlb-specimen")
        XCTAssertEqual(mlb.orange, 0, "the run line is drawn as a projected margin (#8617)")
        XCTAssertGreaterThan(mlb.teal, 300, "control: the played-score line vanished with it")
    }

    /// The same bytes under a sport whose spread IS a margin still draw the
    /// orange line — so the zero above is the gate, not a payload with no
    /// projection or a counter that cannot see orange.
    func testTheSameBytesUnderAMarginSportStillDrawTheProjection() throws {
        let nfl = try ink(sportKey: "americanfootball_nfl", name: "nfl-control")
        XCTAssertGreaterThan(nfl.orange, 300, "control: the specimen's projection does not draw at all")
        XCTAssertGreaterThan(nfl.teal, 300)
    }

    /// Web's page gate opens no empty card for a baseball game with no played
    /// score. The phone's chart returns `EmptyView` when it has no series, so a
    /// projection-only MLB payload renders nothing; the NFL control does not.
    func testAProjectionOnlyMLBPayloadOpensNoCard() throws {
        let mlb = try ink(sportKey: "baseball_mlb", dropScores: true, name: "mlb-no-scores")
        XCTAssertEqual(mlb.orange + mlb.teal, 0, "a baseball card opened on the run line alone")
        let nfl = try ink(sportKey: "americanfootball_nfl", dropScores: true, name: "nfl-no-scores")
        XCTAssertGreaterThan(nfl.orange, 300, "control: a projection-only payload draws under NFL")
    }

    // MARK: - The hero and Game Info (ux ruling, issuecomment-5835251785)

    /// The same run-line pair the backend serves for an MLB game: spread point
    /// 1.5 and total 7.5 solve to 3.0 / 4.5 — the favourite by a run and a half
    /// whatever the price.
    private static let runLineAway = 3.0, runLineHome = 4.5
    private static let now = Date(timeIntervalSince1970: 1_790_000_000)
    private static let beforeTheOff = now.addingTimeInterval(3 * 3600)
    private static let underway = now.addingTimeInterval(-3600)

    /// Before the off the hero prints the projection; baseball withholds it and
    /// the same pair under NFL still prints — so the nil is the sport gate, not
    /// a status or date that #5697's gate already refuses.
    func testTheHeroWithholdsTheRunLineBeforeTheOff() {
        XCTAssertNil(EventDetailView.projectionText(
            sport: "baseball_mlb", status: "scheduled", commenceTime: Self.beforeTheOff,
            projectedHome: Self.runLineHome, projectedAway: Self.runLineAway,
            hasScore: false, now: Self.now),
            "the iPhone hero prints the ±1.5 run line as a projected final (#8617)")
        XCTAssertNil(EventDetailView.projectionText(
            sport: "baseball_npb", status: "scheduled", commenceTime: Self.beforeTheOff,
            projectedHome: Self.runLineHome, projectedAway: Self.runLineAway,
            hasScore: false, now: Self.now))
        let control = EventDetailView.projectionText(
            sport: "americanfootball_nfl", status: "scheduled", commenceTime: Self.beforeTheOff,
            projectedHome: Self.runLineHome, projectedAway: Self.runLineAway,
            hasScore: false, now: Self.now)
        XCTAssertEqual(control.map { $0.hasPrefix("Proj. ") && $0.contains("3-5") }, true,
                       "control: the same pair no longer prints under a margin sport — got \(String(describing: control))")
    }

    /// While live the projection moves to Game Info (#8320) through the same
    /// function; baseball withholds it there too.
    func testGameInfoWithholdsTheRunLineWhileLive() {
        XCTAssertNil(EventDetailView.projectionText(
            sport: "baseball_mlb", status: "live", commenceTime: Self.underway,
            projectedHome: Self.runLineHome, projectedAway: Self.runLineAway,
            hasScore: true, now: Self.now),
            "Game Info prints the ±1.5 run line as a projected final (#8617)")
        XCTAssertNotNil(EventDetailView.projectionText(
            sport: "icehockey_nhl", status: "live", commenceTime: Self.underway,
            projectedHome: Self.runLineHome, projectedAway: Self.runLineAway,
            hasScore: true, now: Self.now),
            "control: a live margin sport with a score keeps its Game Info projection")
    }

    /// The hero and Game Info are withheld by one gate only because both read
    /// the served pair through `projectionText`. A second read of
    /// `projectedHomeScore` in the page would be a print path the gate never
    /// sees, so the set of reads is pinned at the one inside the wrapper.
    func testTheEventPageReadsTheProjectedPairInOnePlace() throws {
        let source = try String(contentsOf: URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift"), encoding: .utf8)
        let reads = source.components(separatedBy: "currentOdds?.projectedHomeScore").count - 1
        XCTAssertEqual(reads, 1, "EventDetailView reads the projected pair outside projectionText")
        XCTAssertEqual(source.components(separatedBy: "projectedHomeScore").count - 1, 1)
    }
}
