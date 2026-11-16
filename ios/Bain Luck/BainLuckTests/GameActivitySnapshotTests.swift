import XCTest
@testable import Bain_Luck

@MainActor
final class GameActivitySnapshotTests: XCTestCase {
    private let scoreClock = Date(timeIntervalSince1970: 1_790_000_000)
    private let probabilityClock = Date(timeIntervalSince1970: 1_790_000_020)

    private func snapshot(status: String = "live", home: Double? = 0.455,
                          away: Double? = 0.545, sport: String? = "baseball_mlb",
                          draw: Double? = nil, scoreClock: Date? = nil,
                          priceClock: Date? = nil) throws -> GameActivitySnapshot {
        try XCTUnwrap(GameActivitySnapshot(eventID: 101, homeTeam: "Giants", awayTeam: "Dodgers",
            status: status, homeScore: 3, awayScore: 2, homeProbability: home,
            awayProbability: away, drawProbability: draw, sport: sport,
            scoreObservedAt: scoreClock, probabilityObservedAt: priceClock))
    }

    func testNumericalExtremesDoNotEndLiveActivity() throws {
        for probability in [0.0, 1.0] {
            let value = try snapshot(home: probability, away: 1 - probability)
            XCTAssertFalse(value.isTerminal)
            XCTAssertEqual(value.lifecycle, .live)
            XCTAssertNotNil(value.probabilityLabel)
            XCTAssertNil(value.resultText)
        }
    }

    func testMissingAndSeparateProducerClocksRemainHonest() throws {
        let missing = try snapshot()
        XCTAssertNil(missing.scoreObservedAt)
        XCTAssertNil(missing.probabilityObservedAt)
        XCTAssertNil(missing.scoreAge(at: scoreClock))
        let value = try snapshot(scoreClock: scoreClock, priceClock: probabilityClock)
        XCTAssertEqual(value.scoreObservedAt, scoreClock)
        XCTAssertEqual(value.probabilityObservedAt, probabilityClock)
        XCTAssertEqual(value.scoreAge(at: probabilityClock), 20)
        XCTAssertEqual(value.probabilityAge(at: probabilityClock), 0)
        XCTAssertNil(value.probabilityAge(at: scoreClock), "A future clock is not a fresh observation")
    }

    func testFinalSuppressesProbabilityAndClosedDoesNotInventWinner() throws {
        let final = try snapshot(status: "completed", home: 1, priceClock: probabilityClock)
        XCTAssertTrue(final.isTerminal)
        XCTAssertNil(final.probabilityLabel)
        XCTAssertNil(final.probabilityObservedAt)
        XCTAssertEqual(final.resultText, "Final · Dodgers 2, Giants 3")
        let closed = try snapshot(status: "closed", home: 1)
        XCTAssertTrue(closed.isTerminal)
        XCTAssertFalse(closed.isFinal)
        XCTAssertNil(closed.probabilityText)
        XCTAssertEqual(closed.resultText, "Closed · result unverified")
        XCTAssertFalse(try snapshot(status: "suspended").isTerminal)
        XCTAssertEqual(try snapshot(status: " FINAL ").lifecycle, .final)
        XCTAssertEqual(try snapshot(status: " CLOSED ").lifecycle, .closed)
        XCTAssertEqual(try snapshot(status: "in_progress").lifecycle, .live)
        XCTAssertEqual(try snapshot(status: "pregame").lifecycle, .scheduled)
        let typed = try XCTUnwrap(GameActivitySnapshot(eventID: 101, homeTeam: "Giants",
            awayTeam: "Dodgers", lifecycle: .final, homeScore: 3, awayScore: 2))
        XCTAssertEqual(typed.resultText, final.resultText)
    }

    func testDrawAndUnknownSportKeepScalarRounding() throws {
        let pair = try snapshot()
        XCTAssertEqual(pair.homeRenderedPercent, renderedDuelPercents(away: 0.545, home: 0.455)[1])
        for value in [try snapshot(sport: "soccer_epl"), try snapshot(draw: 0.1), try snapshot(sport: nil)] {
            XCTAssertEqual(value.homeRenderedPercent, renderedPercent(0.455))
            XCTAssertEqual(value.probabilityLabel, "Giants win · 46%")
        }
    }

    func testInvalidIdentityAndReadingsFailClosed() throws {
        XCTAssertNil(GameActivitySnapshot(eventID: 0, homeTeam: "Giants", awayTeam: "Dodgers", status: "live"))
        XCTAssertNil(GameActivitySnapshot(eventID: 101, homeTeam: "  ", awayTeam: "Dodgers", status: "live"))
        for value in [Double.nan, Double.infinity, -0.01, 1.01] {
            XCTAssertNil(try snapshot(home: value, priceClock: probabilityClock).probabilityText)
            XCTAssertNil(try snapshot(home: value, priceClock: probabilityClock).probabilityObservedAt)
        }
        let final = try XCTUnwrap(GameActivitySnapshot(eventID: 101, homeTeam: "Giants", awayTeam: "Dodgers",
                                                      status: "final", homeScore: -1, awayScore: 2))
        XCTAssertNil(final.homeScore)
        XCTAssertEqual(final.resultText, "Final score unavailable")
    }

    func testCodableRoundTripRetainsIdentityAndProducerTimes() throws {
        let value = try snapshot(scoreClock: scoreClock, priceClock: probabilityClock)
        let restored = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONEncoder().encode(value))
        XCTAssertEqual(restored, value)
        XCTAssertEqual(restored.eventID, 101)
        XCTAssertEqual(restored.probabilityObservedAt, probabilityClock)
    }

    func testDecodedTerminalForecastAndInvalidPercentageAreRejected() throws {
        let value = try snapshot()
        var payload = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
        payload["lifecycle"] = "final"
        XCTAssertThrowsError(try JSONDecoder().decode(GameActivitySnapshot.self,
            from: JSONSerialization.data(withJSONObject: payload)))
        payload["lifecycle"] = "live"
        payload["homeRenderedPercent"] = 101
        XCTAssertThrowsError(try JSONDecoder().decode(GameActivitySnapshot.self,
            from: JSONSerialization.data(withJSONObject: payload)))
        payload["homeRenderedPercent"] = 46
        payload["eventID"] = 0
        XCTAssertThrowsError(try JSONDecoder().decode(GameActivitySnapshot.self,
            from: JSONSerialization.data(withJSONObject: payload)))
    }

    func testFinalTiedScoresNeverClaimAnAuthoritativeDraw() throws {
        let value = try XCTUnwrap(GameActivitySnapshot(eventID: 101, homeTeam: "Chelsea", awayTeam: "Arsenal",
            status: "completed", homeScore: 1, awayScore: 1, sport: "soccer_epl"))
        XCTAssertEqual(value.resultText, "Final · Arsenal 1, Chelsea 1")
    }

    /// #10864 — a state pushed by a server that predates the display fields still
    /// decodes, and a bad display field never costs the reader the score and chance.
    func testDisplayFieldsAreOptionalAndCleanedNeverFatal() throws {
        let legacy = #"{"eventID":7,"homeTeam":"Chiefs","awayTeam":"Jets","lifecycle":"live","#
            + #""homeScore":7,"awayScore":9,"homeRenderedPercent":77}"#
        let old = try JSONDecoder().decode(GameActivitySnapshot.self, from: Data(legacy.utf8))
        XCTAssertEqual(old.homeRenderedPercent, 77)
        XCTAssertNil(old.awayRenderedPercent)
        XCTAssertNil(old.homeAbbreviation)
        XCTAssertNil(old.periodLabel)
        XCTAssertNil(old.projectionLabel)
        let bad = #"{"eventID":7,"homeTeam":"Chiefs","awayTeam":"Jets","lifecycle":"live","homeRenderedPercent":77,"#
            + #""awayRenderedPercent":140,"homeColorHex":"red","awayColorHex":"125740","homeAbbreviation":"","#
            + #""periodLabel":4,"projectedHomeScore":26}"#
        let cleaned = try JSONDecoder().decode(GameActivitySnapshot.self, from: Data(bad.utf8))
        XCTAssertEqual(cleaned.homeRenderedPercent, 77)
        XCTAssertNil(cleaned.awayRenderedPercent)
        XCTAssertNil(cleaned.homeColorHex)
        XCTAssertEqual(cleaned.awayColorHex, "#125740")
        XCTAssertNil(cleaned.homeAbbreviation)
        XCTAssertNil(cleaned.periodLabel)
        XCTAssertNil(cleaned.projectedHomeScore, "Half a projected pair is no pair")
    }

    /// #10864 — the projected final travels whole, labeled, and only beside a live reading.
    func testProjectedFinalIsWholeAndLiveOnly() throws {
        let live = try XCTUnwrap(GameActivitySnapshot(eventID: 7, homeTeam: "Chiefs", awayTeam: "Jets",
            lifecycle: .live, homeScore: 7, awayScore: 9, homeProbability: 0.77, awayProbability: 0.23,
            sport: "americanfootball_nfl", projectedHomeScore: 26, projectedAwayScore: 19,
            projectionLabel: "Projected final"))
        XCTAssertEqual(live.awayRenderedPercent, 23)
        XCTAssertEqual(live.projectedHomeScore, 26)
        XCTAssertEqual(live.projectedAwayScore, 19)
        XCTAssertEqual(try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONEncoder().encode(live)), live)
        let final = try XCTUnwrap(GameActivitySnapshot(eventID: 7, homeTeam: "Chiefs", awayTeam: "Jets",
            lifecycle: .final, homeScore: 27, awayScore: 20, projectedHomeScore: 26,
            projectedAwayScore: 19, projectionLabel: "Projected final"))
        XCTAssertNil(final.projectedHomeScore)
        XCTAssertNil(final.projectionLabel)
        XCTAssertNil(final.awayRenderedPercent)
    }

    // #199 — the Live Activity prints the page headline's tenths, from the same pair rule.
    func testHeadlineTenthsMatchThePageHeadlinePair() throws {
        let value = try XCTUnwrap(GameActivitySnapshot(eventID: 101, homeTeam: "Lions", awayTeam: "Patriots",
            status: "live", homeScore: 21, awayScore: 17, homeProbability: 0.662,
            awayProbability: 0.338, sport: "americanfootball_nfl"))
        let page = EventHeadlineTenths10090.pair(home: 0.662, away: 0.338)
        XCTAssertEqual(value.headlineNowText(home: true), page.home)
        XCTAssertEqual(value.headlineNowText(home: false), page.away)
        XCTAssertEqual(value.headlineNowText(home: true), "66.2%")
        XCTAssertEqual(value.headlineNowText(home: false), "33.8%")
        // A pair that sums off 100 is normalised exactly as the page normalises it.
        let loose = try snapshot(home: 0.5, away: 0.505, sport: "americanfootball_nfl")
        XCTAssertEqual(loose.headlineNowText(home: true),
                       EventHeadlineTenths10090.pair(home: 0.5, away: 0.505).home)
        let restored = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONEncoder().encode(value))
        XCTAssertEqual(restored.headlineNowText(home: true), "66.2%")
    }

    func testHeadlineTenthsAbsentWhereThePageHasNoPair() throws {
        XCTAssertNil(try snapshot(home: 0.5, away: 0.3, draw: 0.2).headlineNowText(home: true),
                     "A draw-priced reading keeps whole numbers")
        XCTAssertNil(try snapshot(home: 0.62, away: 0.30).headlineNowText(home: true),
                     "A pair outside 99-101% has no single tenths line")
        XCTAssertNil(try snapshot(status: "completed", home: 1, away: 0).headlineNowText(home: true))
        XCTAssertEqual(try snapshot(home: 0.9997, away: 0.0003).headlineNowText(home: true), ">99%",
                       "A live reading never prints certainty")
        XCTAssertEqual(try snapshot(home: 0.9997, away: 0.0003).headlineNowText(home: false), "<1%")
    }

    func testDecodedHeadlineTenthsOutOfRangeOrOneSidedAreDropped() throws {
        let value = try snapshot(sport: "americanfootball_nfl")
        var payload = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
        payload["homeHeadlineTenths"] = 1001
        var decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONSerialization.data(withJSONObject: payload))
        XCTAssertNil(decoded.homeHeadlineTenths)
        payload["homeHeadlineTenths"] = 455
        decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONSerialization.data(withJSONObject: payload))
        XCTAssertEqual(decoded.headlineNowText(home: false), "54.5%")
        payload.removeValue(forKey: "awayRenderedPercent")
        decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONSerialization.data(withJSONObject: payload))
        XCTAssertNil(decoded.homeHeadlineTenths, "A one-sided reading has no pair to split")
    }

    /// Direction 209 — the pregame pair is both sides or neither, each 0–100,
    /// and it survives a round trip through the activity's content state.
    func testThePregamePairIsBothOrNeitherAndRoundTrips() throws {
        let both = try XCTUnwrap(GameActivitySnapshot(eventID: 5, homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
            lifecycle: .final, homeScore: 27, awayScore: 20, sport: "americanfootball_nfl", servedResult: "home",
            pregameAwayPercent: 39, pregameHomePercent: 61))
        let decoded = try JSONDecoder().decode(GameActivitySnapshot.self, from: JSONEncoder().encode(both))
        XCTAssertEqual(decoded.pregameAwayPercent, 39)
        XCTAssertEqual(decoded.pregameHomePercent, 61)
        XCTAssertEqual(decoded.sport, "americanfootball_nfl")
        let oneSided = try XCTUnwrap(GameActivitySnapshot(eventID: 5, homeTeam: "A", awayTeam: "B", lifecycle: .final,
            pregameAwayPercent: nil, pregameHomePercent: 61))
        XCTAssertNil(oneSided.pregameHomePercent)
        let outOfRange = #"{"eventID":5,"homeTeam":"A","awayTeam":"B","lifecycle":"final","pregameAwayPercent":140,"pregameHomePercent":61}"#
        let bad = try JSONDecoder().decode(GameActivitySnapshot.self, from: Data(outOfRange.utf8))
        XCTAssertNil(bad.pregameAwayPercent)
        XCTAssertNil(bad.pregameHomePercent)
    }
}
