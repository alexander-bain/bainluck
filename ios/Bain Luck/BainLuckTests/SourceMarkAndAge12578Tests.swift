import XCTest
@testable import Bain_Luck

/// #12578 / #12581 (137-A, Alex, 9:37 PM PT Tue Nov 10) — each prop row carries
/// the quiet source mark, drawn from the server's `source_mark` and never worked
/// out in the app; the sheet is "Where this number comes from".
final class SourceMark12581Tests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_793_000_000)
    private func stamp(_ secondsAgo: Double) -> String {
        now.addingTimeInterval(-secondsAgo).ISO8601Format()
    }

    /// #12581's shape, with stamps relative to the fixed `now` (gotcha #44).
    private func fixture(_ state: String = "blend", settled: String = "null") -> Data {
        """
        {"market_name": "New England vs Detroit: Touchdowns", "outcome_name": "Drake Maye: 1+",
         "threshold": 1, "over_probability": 0.62, "source": "kalshi", "movement": null,
         "player_headshot": null, "player_team": null, "actual": null, "hit": null, "pregame_mark": null,
         "source_mark": {"state": "\(state)",
           "sources": [
             {"key": "kalshi", "name": "Kalshi", "probability": 0.62, "observed_at": "\(stamp(64))"},
             {"key": "polymarket", "name": "Polymarket", "probability": 0.604, "observed_at": "\(stamp(3 * 3600))"},
             {"key": "broken", "probability": "not a number"},
             {"key": "betting", "name": "Sportsbooks", "probability": 0.61, "observed_at": "\(stamp(20))", "count": 5}
           ],
           "settled": \(settled)}}
        """.data(using: .utf8)!
    }

    private func decode(_ data: Data) throws -> GameMarketPlayerProp {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketPlayerProp.self, from: data)
    }

    func testAPropRowCarriesTheServedMarkInItsOrder() throws {
        let mark = try XCTUnwrap(try decode(fixture()).sourceMark)
        XCTAssertEqual(mark.state, .blend)
        XCTAssertEqual(mark.sources.map(\.key), ["kalshi", "polymarket", "betting"],
                       "served order, and the unreadable source drops alone")
        XCTAssertTrue(mark.draws)
    }

    func testTheSheetListsEachSourceWithAWholeNumberPriceAndItsAge() throws {
        let mark = try XCTUnwrap(try decode(fixture()).sourceMark)
        XCTAssertEqual(SourceMarkSheet.title, "Where this number comes from")
        XCTAssertEqual(SourceMarkSheet.lines(mark, now: now), [
            .init(name: "Kalshi", price: "62%", age: "1m ago"),
            .init(name: "Polymarket", price: "60%", age: "3h ago"),
            .init(name: "Sportsbooks (5)", price: "61%", age: "just now"),
        ])
        XCTAssertNil(SourceMarkSheet.settledLine(mark, now: now))
    }

    /// Fable, 10:41 PM Tue + 8:19 AM Wed (139-A, 145-A): the tapped number large
    /// and whole above the rows, one line of method below, and "Bain Luck blend"
    /// only where the mark is a blend of more than one source.
    func testTheSheetRepeatsTheNumberAndSaysHowItWasMade() throws {
        let blend = try XCTUnwrap(try decode(fixture()).sourceMark)
        XCTAssertEqual(SourceMarkSheet.headline(0.624), "62%")
        XCTAssertNil(SourceMarkSheet.headline(nil))
        XCTAssertEqual(SourceMarkSheet.method(blend), "Bain Luck blend, weighted by freshness and depth")
        let prop = SourceMark(state: .blend, sources: [
            .init(key: "kalshi", name: "Kalshi", probability: 0.62, observedAt: nil)])
        XCTAssertEqual(SourceMarkSheet.method(prop), "Kalshi's price", "one venue is named, never called a blend")
        XCTAssertEqual(SourceMarkSheet.lines(prop, now: now), [.init(name: "Kalshi", price: "62%", age: nil)],
                       "no observation time, no age")
        XCTAssertNil(SourceMarkSheet.method(SourceMark(state: .settled, sources: [], settled: .init(source: "kalshi", result: "Yes", at: nil))))
    }

    func testTheMarkIsTheInfoRing() throws {
        let source = try Self.source("Bain Luck/Components/SourceMarkView12581.swift")
        XCTAssertTrue(source.contains("Image(systemName: \"info.circle\")"), "139-A: the ⓘ ring")
    }

    func testASettledNumberSaysOfficialResultFirst() throws {
        let data = fixture("settled", settled: "{\"source\": \"kalshi\", \"result\": \"Yes\", \"at\": \"\(stamp(7200))\"}")
        let mark = try XCTUnwrap(try decode(data).sourceMark)
        XCTAssertEqual(SourceMarkSheet.settledLine(mark, now: now), .init(name: "Official result", price: "Yes", age: "2h ago"))
    }

    func testNothingToSayDrawsNoMark() throws {
        XCTAssertNil(SourceMarkButton(nil, numberSize: 20), "an unserved mark draws nothing: the app never infers one")
        XCTAssertNil(SourceMarkButton(try decode(fixture("none")).sourceMark, numberSize: 20))
        XCTAssertNil(SourceMarkButton(try decode(fixture("someday")).sourceMark, numberSize: 20), "an unknown state")
        XCTAssertNil(SourceMarkButton(SourceMark(state: .blend, sources: []), numberSize: 20), "never an empty sheet")
        XCTAssertNotNil(SourceMarkButton(try decode(fixture()).sourceMark, numberSize: 20))
    }

    func testAMalformedMarkNeverTakesTheRowDown() throws {
        let json = #"{"market_name": "M", "outcome_name": "P: 1+", "threshold": 1, "over_probability": 0.5, "source": "kalshi", "movement": null, "player_headshot": null, "player_team": null, "actual": null, "hit": null, "pregame_mark": null, "source_mark": "kalshi"}"#
        let prop = try decode(Data(json.utf8))
        XCTAssertEqual(prop.overProbability, 0.5)
        XCTAssertEqual(prop.sourceMark?.draws, false)
    }

    func testOneSourceAndTwoSourcesDrawTheSameRing() throws {
        XCTAssertEqual(SourceMarkButton.ringScale, 0.7)
        let one = try XCTUnwrap(SourceMarkButton(SourceMark(state: .blend, sources: [
            .init(key: "kalshi", name: "Kalshi", probability: 0.6, observedAt: nil)]), numberSize: 20))
        let two = try XCTUnwrap(SourceMarkButton(try decode(fixture()).sourceMark, numberSize: 20))
        XCTAssertEqual(one.numberSize, two.numberSize)
        // The ring has no branch on what it stands for: no letter, no count, no venue.
        let source = try Self.source("Bain Luck/Components/SourceMarkView12581.swift")
        let body = try XCTUnwrap(source.range(of: "Button { open = true } label: {"))
        let label = String(source[body.upperBound...].prefix(400))
        for varying in ["mark.sources", "mark.state", "Text(", "count"] {
            XCTAssertFalse(label.contains(varying), "the ring does not vary with \(varying)")
        }
    }

    func testEveryPropNumberCarriesTheMark() throws {
        let source = try Self.source("Bain Luck/Components/PlayerPropsCardView.swift")
        XCTAssertTrue(source.contains("SourceMarkButton(target.rung.sourceMark, number: target.rung.probability, numberSize: targetNumberSize)"))
        XCTAssertTrue(source.contains("SourceMarkButton(rung.sourceMark, number: rung.probability, numberSize: rungNumberSize)"))
        XCTAssertTrue(source.contains("sourceMark: prop.sourceMark"))
    }

    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }
}

/// #12578 (Alex: "isn't it actually obvious from the x-axis when the projection
/// is from?") — no grey sentence; an age mark only when the projection is stale.
/// And Fable on the started card: the score line opens at 0–0 from kickoff when
/// the data says the game began there.
@MainActor
final class ProjectedAgeAndOpeningScore12578Tests: XCTestCase {
    private typealias Series = ProjectedFinalPointsSeries
    private let epoch = Date(timeIntervalSince1970: 1_790_000_000)
    private func t(_ seconds: Double) -> Date { epoch.addingTimeInterval(seconds) }
    private func pair(_ seconds: Double, _ home: Double = 27, _ away: Double = 20) -> Series.Pair {
        .init(at: t(seconds), home: home, away: away, homeProbability: 0.6, kind: .recorded)
    }
    private func input(_ pairs: [Series.Pair], actuals: [Series.Actual] = [], floor: Double? = 0,
                       final: Double? = nil, now: Double = 1800, opening: Series.Actual? = nil) -> Series.Input {
        var input = Series.Input(sportKey: "americanfootball_nfl", sourceKey: "draftkings",
                                 basis: .sameBookSameCaptureFullGameSpreadAndTotal, pairs: pairs, actuals: actuals,
                                 kickoffAt: nil, scoreObservationStartAt: floor.map(t), finalAt: final.map(t),
                                 asOf: t(now), windowStartAt: nil, requestCutoffAt: nil)
        input.openingScore = opening
        return input
    }

    // MARK: - The age mark

    func testAFreshProjectionShowsNoAge() throws {
        let series = try XCTUnwrap(Series.build(input([pair(-600)], floor: nil, now: 0)))
        XCTAssertNil(ProjectedFinalPointsChartView.ageMark(for: series, now: t(0)), "10 minutes old is inside the cadence")
    }

    func testAStaleProjectionShowsItsAgeAsTheAppsMark() throws {
        let series = try XCTUnwrap(Series.build(input([pair(-5 * 3600)], floor: nil, now: 0)))
        let mark = try XCTUnwrap(ProjectedFinalPointsChartView.ageMark(for: series, now: t(0)))
        XCTAssertEqual(mark.age, "5h ago")
    }

    func testAFinishedGameShowsNoAge() throws {
        let series = try XCTUnwrap(Series.build(input([pair(-600), pair(600)],
                                                      actuals: [.init(at: t(3000), home: 24, away: 17)],
                                                      final: 3600, now: 3600)))
        XCTAssertNil(ProjectedFinalPointsChartView.ageMark(for: series, now: t(90_000)))
    }

    func testTheCardHasNoRecordedSentence() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/ProjectedFinalPointsChartView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let readout = try XCTUnwrap(source.range(of: "private func readout("))
        let body = String(source[readout.upperBound...].prefix(1200))
        XCTAssertFalse(body.contains("recordedLine"), "the readout prints no recorded sentence")
        XCTAssertTrue(body.contains("Self.ageMark(for: series, now: input.asOf)"))
    }

    // MARK: - The score from kickoff

    func testTheScoreOpensAtZeroZeroAtKickoffAheadOfTheFirstCapture() throws {
        let series = try XCTUnwrap(Series.build(input(
            [pair(-600, 24, 21), pair(1200, 30, 17)],
            actuals: [.init(at: t(1200), home: 7, away: 0)], now: 1800,
            opening: .init(at: t(0), home: 0, away: 0))))
        XCTAssertEqual(series.actualSteps.first, .init(at: t(0), home: 0, away: 0))
        XCTAssertEqual(series.actualSteps.count, 2)
        XCTAssertTrue(series.scoreOpensAtFloor)
        XCTAssertNil(ProjectedFinalPointsChartView.scoreStartNote(for: series))
        XCTAssertEqual(series.latestActual, .init(at: t(1200), home: 7, away: 0), "the readout's score is unchanged")
    }

    func testWithoutAnOpeningTheLineStartsAtTheFirstCaptureAndSaysSo() throws {
        let series = try XCTUnwrap(Series.build(input(
            [pair(-600, 24, 21), pair(1200, 30, 17)],
            actuals: [.init(at: t(1200), home: 7, away: 0)], now: 1800)))
        XCTAssertEqual(series.actualSteps.first?.at, t(1200))
        XCTAssertFalse(series.scoreOpensAtFloor)
        XCTAssertEqual(ProjectedFinalPointsChartView.scoreStartNote(for: series),
                       "The dashed score line starts at the first recorded score.")
    }

    func testAnOpeningAloneClaimsNothingAboutNow() throws {
        let series = try XCTUnwrap(Series.build(input(
            [pair(-600, 24, 21), pair(1200, 30, 17)], now: 1800,
            opening: .init(at: t(0), home: 0, away: 0))))
        XCTAssertTrue(series.actualSteps.isEmpty, "no recorded score yet, so no 0–0 held to now")
        XCTAssertFalse(series.scoreOpensAtFloor)
    }

    func testTheOpeningComesFromTheFloorsOwnEvidence() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        func history(_ espn: String) throws -> EventHistoryResponse {
            try decoder.decode(EventHistoryResponse.self, from: Data("""
            {"event_id": 1, "home_team": "Detroit Lions", "away_team": "New England Patriots",
             "sport_key": "americanfootball_nfl", "status": "live", "history": [], "espn_history": \(espn)}
            """.utf8))
        }
        let at = t(0)
        let marker = ProjectedFinalPointsMount.ObservedFloor(at: at, basis: .periodMarkerStart)
        XCTAssertEqual(ProjectedFinalPointsMount.openingScore(marker, history: try history("[]")),
                       .init(at: at, home: 0, away: 0), "a first-period start marker is before play: 0–0")
        let sighting = ProjectedFinalPointsMount.ObservedFloor(at: at, basis: .espnFirstPeriodSighting)
        let stamp = at.ISO8601Format()
        XCTAssertEqual(ProjectedFinalPointsMount.openingScore(sighting, history: try history(
            #"[{"timestamp": "\#(stamp)", "period": "1st Quarter", "home_score": 3, "away_score": 0}]"#)),
                       .init(at: at, home: 3, away: 0), "a sighting opens at the score it saw")
        XCTAssertNil(ProjectedFinalPointsMount.openingScore(sighting, history: try history(
            #"[{"timestamp": "\#(stamp)", "period": "1st Quarter"}]"#)), "a sighting with no score says nothing")
    }
}
