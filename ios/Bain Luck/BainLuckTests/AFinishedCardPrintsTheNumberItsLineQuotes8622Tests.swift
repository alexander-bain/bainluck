import Foundation
import XCTest
@testable import Bain_Luck

/// #8622 (the iPhone half of #8315): a finished game's card prints the same
/// pre-match number as the line under it.
///
/// The server resolves Alex's ladder (Kalshi, then Polymarket, then
/// sportsbooks) once, serves it as `prematch_odds`, and writes the card's
/// reason line from it. The phone never decoded the key and printed
/// `opening_odds`, the sportsbook median. On the Sports tab, 2026-09-25:
/// "Leylah Fernandez 24%" over "Leylah Fernandez won as a 22% underdog".
///
/// Specimen: event 15317920 (Mirra Andreeva v Leylah Fernandez, 0–2) as
/// `/api/feed?mode=sports` served it at 13:20Z.
final class AFinishedCardPrintsTheNumberItsLineQuotes8622Tests: XCTestCase {

    private static let prematchJSON = """
    {"home_probability": 0.775, "away_probability": 0.225,
     "home_rendered_percent": 78, "away_rendered_percent": 22, "source": "kalshi"}
    """
    private static let openingJSON = """
    {"home_probability": 0.7619, "away_probability": 0.2381, "favorite": "home"}
    """

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func prematch(_ json: String) throws -> PrematchOdds {
        try decoder().decode(PrematchOdds.self, from: Data(json.utf8))
    }

    private func opening(_ json: String) throws -> OpeningOdds {
        try decoder().decode(OpeningOdds.self, from: Data(json.utf8))
    }

    // MARK: - The payload reaches the models

    func testTheFeedEventDecodesTheServedReading() throws {
        let event = try decoder().decode(FeedEventData.self, from: Data("""
        {"id": 15317920, "home_team": "Mirra Andreeva", "away_team": "Leylah Fernandez",
         "status": "completed", "home_score": 0, "away_score": 2,
         "opening_odds": \(Self.openingJSON), "prematch_odds": \(Self.prematchJSON)}
        """.utf8))
        XCTAssertEqual(event.prematchOdds?.awayRenderedPercent, 22)
        XCTAssertEqual(event.prematchOdds?.source, "kalshi")
    }

    func testTheEventDetailDecodesTheServedReading() throws {
        let event = try decoder().decode(EventDetail.self, from: Data("""
        {"id": 15317920, "home_team": "Mirra Andreeva", "away_team": "Leylah Fernandez",
         "status": "completed", "opening_odds": \(Self.openingJSON),
         "prematch_odds": \(Self.prematchJSON)}
        """.utf8))
        XCTAssertEqual(event.prematchOdds?.homeRenderedPercent, 78)
    }

    // MARK: - The rule (web's `lib/prematchReading.ts`)

    func testTheServedReadingWinsOverTheSportsbookMedian() throws {
        let reading = try XCTUnwrap(PrematchReading.resolve(
            prematch: prematch(Self.prematchJSON), opening: opening(Self.openingJSON)))
        XCTAssertEqual(reading.percents, [22, 78], "the reason line's number, not the median's 24")
        XCTAssertEqual(reading.awayProbability, 0.225)
        XCTAssertEqual(reading.source, "kalshi")
        XCTAssertTrue(reading.isServed)
        XCTAssertEqual(reading.captionWord, "Pre-match", "a Kalshi last price is not an opening line")
    }

    func testAnAbsentKeyFallsBackToTheOpeningLine() throws {
        let reading = try XCTUnwrap(PrematchReading.resolve(
            prematch: nil, opening: opening(Self.openingJSON)))
        XCTAssertEqual(reading.percents, [24, 76])
        XCTAssertEqual(reading.source, PrematchReading.booksSource)
        XCTAssertFalse(reading.isServed)
        XCTAssertEqual(reading.captionWord, "Opened")
    }

    /// Both served values or neither (#2279): a served 22 beside a locally
    /// rounded home would re-open the 101 UX-P114 closed.
    func testOneServedPercentIsNotHalfAPair() throws {
        let reading = try XCTUnwrap(PrematchReading.resolve(prematch: prematch("""
        {"home_probability": 0.505, "away_probability": 0.495,
         "home_rendered_percent": 51, "source": "kalshi"}
        """), opening: nil))
        XCTAssertEqual(reading.percents, renderedDuelPercents(away: 0.495, home: 0.505))
        XCTAssertEqual(reading.percents.compactMap { $0 }.reduce(0, +), 100)
    }

    func testAMissingAwayIsTheComplement() throws {
        let reading = try XCTUnwrap(PrematchReading.resolve(prematch: prematch("""
        {"home_probability": 0.7, "source": "polymarket"}
        """), opening: nil))
        XCTAssertEqual(reading.awayProbability, 0.3, accuracy: 1e-9)
    }

    /// A pre-match 0 or 1 is a settled price leaking backwards; it must not
    /// win the ladder or print as the strongest claim on the card.
    func testASettledEndpointIsNotAPrematchReading() throws {
        let fell = try XCTUnwrap(PrematchReading.resolve(prematch: prematch("""
        {"home_probability": 1.0, "away_probability": 0.0, "source": "kalshi"}
        """), opening: opening(Self.openingJSON)))
        XCTAssertFalse(fell.isServed, "an unusable served reading falls through to the opening line")
        let settledOpening = try opening("""
        {"home_probability": 0.0, "away_probability": 1.0}
        """)
        XCTAssertNil(PrematchReading.resolve(prematch: nil, opening: settledOpening))
        XCTAssertNil(PrematchReading.resolve(prematch: nil, opening: nil))
    }

    // MARK: - The surfaces read the rule, not the field

    private static func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
    }

    /// The body of `name` up to the next declaration at the same indent.
    private static func body(of name: String, in text: String) throws -> String {
        let start = try XCTUnwrap(text.range(of: name), "\(name) moved; move this test with it")
        let rest = text[start.upperBound...]
        let end = rest.range(of: "\n    @ViewBuilder\n")?.lowerBound
            ?? rest.range(of: "\n    private ")?.lowerBound
            ?? rest.endIndex
        return String(rest[..<end])
    }

    func testTheFinishedRowAndBarReadTheResolvedReading() throws {
        let card = try Self.source("Bain Luck/Components/EventCardView.swift")
        let row = try Self.body(of: "private func preGameOddsLabel(", in: card)
        XCTAssertTrue(row.contains("prematch"), "the finished row prints the resolved reading")
        XCTAssertFalse(row.contains("openingOdds"), "the finished row must not read the median directly")
        XCTAssertFalse(row.contains("openingPercents"), "nor round the median's pair")
        let bar = try Self.body(of: "private var probabilityBar:", in: card)
        let settledArm = try XCTUnwrap(bar.components(separatedBy: "} else if isSuspended").first)
        XCTAssertTrue(settledArm.contains("prematch"), "the settled bar draws the resolved reading")
        XCTAssertFalse(settledArm.contains("openingOdds"))
        XCTAssertTrue(card.contains("PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)"))
    }

    func testTheSettledHeroCaptionReadsTheResolvedReading() throws {
        try TestSuiteDisposition12982.skipSuperseded(#function, by: "Direction 199 / Ruling 200-B settled Pregame · Final columns — covered by UnifiedHeadlineContactSheetGuard199Tests")
        let page = try Self.source("Bain Luck/Views/EventDetailView.swift")
        let hero = try Self.body(of: "private func heroSection(", in: page)
        let wiring = hero.filter { !$0.isWhitespace }
        XCTAssertTrue(wiring.contains("letsportHeadline12472=EventSportHeadlines12472.resolve("))
        XCTAssertTrue(wiring.contains("EventSportHeadlineCard12472(model:sportHeadline12472,"))

        func headline(prematch: String) throws -> EventSportHeadlines12472.Model {
            let event = try decoder().decode(EventDetail.self, from: Data("""
            {"id": 15317920, "home_team": "Mirra Andreeva", "away_team": "Leylah Fernandez",
             "sport": "tennis_wta", "status": "completed", "home_score": 0, "away_score": 2,
             "opening_odds": \(Self.openingJSON), "prematch_odds": \(prematch)}
            """.utf8))
            return EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: Date(timeIntervalSince1970: 1_790_000_000)
            )
        }

        let served = try headline(prematch: Self.prematchJSON)
        let openingOnly = try headline(prematch: "null")
        XCTAssertEqual(served.kind, .tennisAfterGame)
        XCTAssertEqual(served.columns.map(\.role), [.pregame, .finalResult])
        XCTAssertEqual(served.columns.map(\.header), ["Pregame", "Final"])
        XCTAssertEqual(served.rows.map(\.fullName), ["Leylah Fernandez", "Mirra Andreeva"])
        XCTAssertEqual(served.rows.map(\.cells), [["22%", "2"], ["78%", "0"]])
        XCTAssertEqual(served.rows.map(\.won), [true, false])
        XCTAssertEqual(openingOnly.columns.map(\.role), served.columns.map(\.role))
        XCTAssertEqual(openingOnly.columns.map(\.header), ["", "Final"])
        XCTAssertEqual(openingOnly.rows.map(\.cells), [["", "2"], ["", "0"]])
        XCTAssertEqual(openingOnly.rows.map(\.won), served.rows.map(\.won))
    }
}
