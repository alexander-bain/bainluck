import XCTest
@testable import Bain_Luck

/// #10864 — a final Live Activity names the winner only from the server's own
/// verdict (`hero_settled_result`), never from the scores.
final class GameActivityServedResult10864Tests: XCTestCase {

    private func snapshot(_ lifecycle: GameActivitySnapshot.Lifecycle, served: String?,
                          home: Int = 1, away: Int = 1) -> GameActivitySnapshot? {
        GameActivitySnapshot(eventID: 7, homeTeam: "Villarreal", awayTeam: "Getafe", lifecycle: lifecycle,
                             homeScore: home, awayScore: away, sport: "soccer_spain_la_liga",
                             servedResult: served)
    }

    func testAFinalKeepsTheServersVerdict() throws {
        XCTAssertEqual(try XCTUnwrap(snapshot(.final, served: "home")).result, .home)
        XCTAssertEqual(try XCTUnwrap(snapshot(.final, served: "away")).result, .away)
        XCTAssertEqual(try XCTUnwrap(snapshot(.final, served: "draw")).result, .draw)
    }

    func testALevelScoreSettledAnotherWayKeepsItsWinner() throws {
        // 1–1 decided on penalties: the scores alone say nothing, the server says away.
        let shootout = try XCTUnwrap(snapshot(.final, served: "away", home: 1, away: 1))
        XCTAssertEqual(shootout.result, .away)
    }

    func testNoVerdictIsEverReadOffTheScores() throws {
        XCTAssertNil(try XCTUnwrap(snapshot(.final, served: nil, home: 3, away: 0)).result)
        XCTAssertNil(try XCTUnwrap(snapshot(.final, served: "HOME", home: 3, away: 0)).result,
                     "an unrecognised verdict is no verdict")
    }

    func testOnlyAFinalCarriesAVerdict() throws {
        XCTAssertNil(try XCTUnwrap(snapshot(.live, served: "home")).result)
        XCTAssertNil(try XCTUnwrap(snapshot(.closed, served: "home")).result)
        XCTAssertNil(try XCTUnwrap(snapshot(.suspended, served: "home")).result)
    }

    func testTheVerdictSurvivesTheTripToTheWidget() throws {
        let final = try XCTUnwrap(snapshot(.final, served: "away"))
        let decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONEncoder().encode(final))
        XCTAssertEqual(decoded.result, .away)
    }

    func testAnOlderPayloadWithoutAVerdictStillDecodes() throws {
        let json = #"{"eventID":7,"homeTeam":"Villarreal","awayTeam":"Getafe","lifecycle":"final","homeScore":2,"awayScore":1}"#
        let decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: Data(json.utf8))
        XCTAssertNil(decoded.result)
        let malformed = #"{"eventID":7,"homeTeam":"V","awayTeam":"G","lifecycle":"final","result":"won"}"#
        XCTAssertNil(try JSONDecoder().decode(GameActivitySnapshot.self, from: Data(malformed.utf8)).result)
    }

    func testTheGamePagePassesTheServersVerdict() throws {
        let source = try Self.source("Bain Luck/Utilities/GameActivitySnapshot+Event.swift")
        XCTAssertTrue(source.contains("servedResult: event.heroSettledResult"))
    }

    func testTheCardsVerdictComesOnlyFromTheSnapshot() throws {
        let view = try Self.source("BainLuckWidget/GameLiveActivity.swift").filter { !$0.isWhitespace }
        XCTAssertTrue(view.contains("guardmatches,snapshot.isFinal,letresult=snapshot.resultelse{returnnil}"),
                      "the verdict reads the server's result and nothing else")
        XCTAssertTrue(view.contains("casenil:returnlowerScoredSide"), "without a verdict the scoreboard rule stands")
        XCTAssertTrue(view.contains("}elseifletverdict=reading.verdict(side){"), "the row prints the verdict")
    }

    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
