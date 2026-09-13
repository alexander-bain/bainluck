import XCTest
@testable import Bain_Luck

/// #5697 AC2, the iOS half — A PROJECTED FINAL NEEDS A GAME WHOSE STATE THE
/// READER CAN SEE.
///
/// THE SPECIMEN, read off production 2026-09-13 06:20Z: event **15311077**,
/// Fukuoka SoftBank Hawks v Chiba Lotte Marines (NPB). `status='live'`,
/// `home_score` and `away_score` both null, nearly two hours past its own first
/// pitch, `current_odds.projected_home_score = 7.0` / `projected_away_score =
/// 5.5` captured minutes earlier. The hero drew `Projected final 6-7 runs` —
/// a confident pair shaped exactly like a scoreline, with no score anywhere on
/// the screen to read it against. 1 of the 3 live events carrying a projection
/// at that minute was in this state.
///
/// THE NUMBER IS FRESH AND THAT IS NOT THE POINT. The projection is derived from
/// the live spread and total (`odds_math.project_scores`), so it moves with play
/// even while our score feed is dark — that was measured before this was built,
/// because "it is stale" would have been the easy argument and it is not true.
/// The defect is that a projected FINAL only means something against how much
/// game is left. A reader who cannot see the score cannot tell the first inning
/// from the ninth, so a fresh, correct `7 - 5.5` still carries no information
/// while looking exactly like information. Before the off the frame IS known —
/// nothing has happened — so the same forecast is honest and stays.
///
/// Twin of the web's `projectionHasGameStateToFrame` (#5803, `ade48eb95`),
/// handed over by ux/1225 under notice 41.
final class LiveProjectionNeedsAScore5697Tests: XCTestCase {

    /// Gotcha #44 — offsets from a literal instant, never a branch on the real
    /// clock. Every assertion passes `now:` explicitly, so nothing here ages.
    private static let now = Date(timeIntervalSince1970: 1_788_000_000)
    private static let started = now.addingTimeInterval(-2 * 3600)
    private static let notYet = now.addingTimeInterval(2 * 3600)

    /// The composition the view actually performs, in one place: the hero's
    /// `hasScore` is `showsScore`, and that is what gates the projection.
    /// Pinned to the real call site by `testTheViewWiresTheGateToTheScoreItDraws`
    /// below — without that scan this helper would be a model agreeing with
    /// itself.
    private static func heroDrawsProjection(
        status: String?, away: Int?, home: Int?, commenceTime: Date?, now: Date
    ) -> Bool {
        EventDetailView.showsProjection(
            status: status,
            commenceTime: commenceTime,
            hasScore: EventDetailView.showsScore(status: status, away: away, home: home),
            now: now)
    }

    // MARK: - The defect

    func testTheSpecimenWithholdsItsProjectedFinal() {
        XCTAssertFalse(
            Self.heroDrawsProjection(
                status: "live", away: nil, home: nil,
                commenceTime: Self.started, now: Self.now),
            "15311077 drew a projected final over a game with no score")
    }

    // MARK: - The controls — what must NOT change

    /// Kills the mutant that deletes the projection outright. Before kickoff a
    /// forecast is the honest thing and is the whole point of the row.
    func testAForecastBeforeTheOffIsHonestAndStays() {
        XCTAssertTrue(
            Self.heroDrawsProjection(
                status: "scheduled", away: nil, home: nil,
                commenceTime: Self.notYet, now: Self.now),
            "a pre-game projection was withdrawn; #5697 AC2 does not ask for that")
    }

    /// The other half of that control: underway, but the reader can see the
    /// score, so the forecast has its frame and stays.
    func testALiveGameShowingItsScoreKeepsItsProjection() {
        XCTAssertTrue(
            Self.heroDrawsProjection(
                status: "live", away: 3, home: 4,
                commenceTime: Self.started, now: Self.now),
            "a live game with a score on screen lost a projection that was fine")
    }

    // MARK: - The axis mutants

    /// Kills `underway = (status == "live")`. A row whose status has not caught
    /// up with its own clock is underway to the reader and must be treated so.
    func testARowPastItsStartTimeIsUnderwayWhateverItsStatusSays() {
        XCTAssertFalse(
            Self.heroDrawsProjection(
                status: "scheduled", away: nil, home: nil,
                commenceTime: Self.started, now: Self.now),
            "a scheduled row two hours past its start still projected over no score")
    }

    /// Kills `!underway` being dropped (gate collapsing to `hasScore`). Stated
    /// as the pair of outcomes that differ only in whether the game has begun.
    func testTheGateTurnsOnWhetherTheGameHasBegun() {
        let before = Self.heroDrawsProjection(
            status: "scheduled", away: nil, home: nil,
            commenceTime: Self.notYet, now: Self.now)
        let after = Self.heroDrawsProjection(
            status: "scheduled", away: nil, home: nil,
            commenceTime: Self.started, now: Self.now)
        XCTAssertTrue(before, "the same scoreless row must keep its projection before the off")
        XCTAssertFalse(after, "and lose it once underway")
    }

    /// THE PAIR, NOT A SIDE. A half-reported score is not a frame: the reader
    /// would be comparing a projected pair against a single number. `showsScore`
    /// already refuses a lone side, and the gate inherits that refusal — this
    /// pins the inheritance, which is what the web half's per-side mutant tests.
    func testAHalfReportedScoreIsNotAScore() {
        for (away, home) in [(3, nil), (nil, 4)] as [(Int?, Int?)] {
            XCTAssertFalse(
                Self.heroDrawsProjection(
                    status: "live", away: away, home: home,
                    commenceTime: Self.started, now: Self.now),
                "a lone score side framed a projection (away: \(String(describing: away)), home: \(String(describing: home)))")
        }
    }

    // MARK: - #4002 and #4018 still hold

    /// The score term must not have bought back the states `canStillBeGraded`
    /// already refused — the 184 suspended games, and every finished one.
    func testTheStatesTheProjectionAlreadyRefusedStayRefused() {
        for status in ["completed", "closed"] {
            XCTAssertFalse(
                Self.heroDrawsProjection(
                    status: status, away: 3, home: 4,
                    commenceTime: Self.started, now: Self.now),
                "a finished game (\(status)) projected a final")
        }
        XCTAssertFalse(
            Self.heroDrawsProjection(
                status: "suspended", away: 3, home: 4,
                commenceTime: Self.started, now: Self.now),
            "a suspended game projected a final it will never be given")
    }

    // MARK: - The source scan: the helper above is wired to the real view

    /// Walked from this test's own location, the idiom the other scans use.
    private func eventDetailSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// 🔴 COMMENTS STRIPPED FIRST. Every claim below is about CODE. A scan that
    /// reads the whole file is satisfied by the prose the fix wrote next to the
    /// line it is checking, and then it passes forever for the wrong reason.
    private func eventDetailCode() throws -> String {
        let stripped = try eventDetailSource()
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
        return stripped.split(whereSeparator: { $0 == " " || $0 == "\n" || $0 == "\t" })
            .joined(separator: " ")
    }

    /// Anti-vacuity: if this fails every scan below is asserting about the
    /// wrong file, or about nothing.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try eventDetailCode()
        XCTAssertGreaterThan(code.count, 5_000, "the scan read something far too short to be EventDetailView")
        XCTAssertTrue(code.contains("static func showsProjection"),
                      "the scan did not find showsProjection's own declaration")
        XCTAssertTrue(code.contains("static func showsScore"),
                      "the scan did not find showsScore's own declaration")
    }

    /// The scan that makes `heroDrawsProjection` above mean something: the view
    /// must gate the projection on the same value it draws the score from. A
    /// gate reading `event.homeScore` directly would pass every other test in
    /// this file — it is the iOS form of the web half's payload-vs-row mutant.
    func testTheViewWiresTheGateToTheScoreItDraws() throws {
        let code = try eventDetailCode()
        XCTAssertTrue(
            code.contains("let hasScore = EventDetailView.showsScore("),
            "the hero stopped deriving hasScore from showsScore")
        XCTAssertTrue(
            code.contains("hasScore: hasScore)"),
            "showsProjection is no longer passed the hero's own hasScore")
    }

    /// #3014's label is retired, not merely unused: the string must be gone from
    /// the code, or a later reader will wire it back to a branch that can no
    /// longer fire.
    func testTheSpelledOutLabelIsGoneFromTheCode() throws {
        let code = try eventDetailCode()
        XCTAssertFalse(code.contains("Projected final"),
                       "\"Projected final\" is still in the code; #5697 AC2 removed its only population")
        XCTAssertFalse(code.contains("projectionLabel"),
                       "projectionLabel survived; every input it has left returns \"Proj.\"")
        XCTAssertTrue(code.contains("\"Proj. \\("),
                      "the abbreviation the hero still draws is gone too — that is not this ship")
    }
}
