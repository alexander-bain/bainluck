import XCTest
@testable import Bain_Luck

/// #4982 — on ONE rendered event page, the reader is told at most once that we
/// do not hold the played count.
///
/// The defect, photographed on the Sabalenka–Pegula US Open semi (event
/// 15308357, iPhone 17, 4:29pm PT Thu 2026-09-10, `artifacts-native-020/
/// n107-usopen-live-s500.png` and `-s900.png`): two cards, one below the other,
/// each ending on the same admission.
///
/// > **Score Differential** — Played games are not captured yet, the scoreboard
/// > reports sets. The line below is the sportsbooks' projected game margin.
///
/// > **Games map** — The scoreboard reports sets, this market quotes games — we
/// > do not hold the games played yet.
///
/// Neither view was wrong on its own; each already dedups WITHIN itself (#3503
/// is why the map prints one footnote under all its maps rather than one per
/// card). Nothing arbitrated ACROSS them, and neither can see the other, so two
/// correct single prints landed as one repeated admission. D102 / notice 34.
///
/// 🔴 **THE ASSERTION IS A COUNT OVER TWO COMPONENTS, WHICH IS WHY BOTH RULES
/// HAD TO COME OUT OF THEIR VIEWS.** A test that could only rasterise
/// `MarketMapView` could never see what the chart above it said. So this file
/// reads the two decision functions together — the only place the page-level
/// guard can actually be stated — and every case below asserts BOTH halves, not
/// just the one that changed.
///
/// Sibling: #4969, the web half (ux). No shared code: `playedCountAbsence()` in
/// `frontend/lib/marketMapUtils.ts` has no Swift counterpart, and the iOS
/// sentences are not even the same words, so that fix cannot reach this.
final class PlayedCountAbsenceArbitrationTests: XCTestCase {

    // Tennis is the whole population: the sentences exist only where the
    // scoreboard does not count the unit the markets quote.
    private let tennis = SportVocab.forSport("tennis_wta_us_open")
    private let baseball = SportVocab.forSport("baseball_mlb")

    private static let commence = "2026-09-10T23:00:00Z"

    /// An `EventHistoryResponse` carrying `count` projected-margin points, the
    /// first of them `offsetMinutes` after the match starts.
    ///
    /// Negative offsets are how the "points that all predate the first ball"
    /// case is built — see `testPointsBeforeTheFirstBallDoNotCountAsASeries`.
    private func history(count: Int, offsetMinutes: Double = 0) throws -> EventHistoryResponse {
        let start = Self.commence.asDate!
        let iso = ISO8601DateFormatter()
        let points = (0 ..< count).map { step -> String in
            let at = iso.string(from: start.addingTimeInterval((offsetMinutes + Double(step)) * 60))
            return """
                {"timestamp": "\(at)", "home_probability": 0.6,
                 "projected_home_score": 9.5, "projected_away_score": 8.0}
                """
        }
        let json = """
        {"event_id": 15308357, "home_team": "Jessica Pegula",
         "away_team": "Aryna Sabalenka", "status": "live",
         "history": [\(points.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// How many of the two sentences a page would print, given what the chart
    /// decided. The map is asked the question it is really asked on screen: a
    /// live tennis page whose maps DID withhold a tile.
    private func sentencesOnScreen(
        chartSpeaks: Bool,
        vocab: SportVocab,
        isLive: Bool,
        isDone: Bool,
        mapWithheldATile: Bool = true
    ) -> Int {
        let mapNote = MarketMapRail.mapUnitMismatchNote(
            vocab: vocab,
            statedAbove: chartSpeaks,
            isLive: isLive,
            isDone: isDone,
            mapWithheldATile: mapWithheldATile
        )
        return (chartSpeaks ? 1 : 0) + (mapNote == nil ? 0 : 1)
    }

    // MARK: - The photographed page

    func testTheLiveTennisPageSaysItOnceNotTwice() throws {
        let chartSpeaks = ScoreDifferentialChartView.statesPlayedCountAbsence(
            history: try history(count: 12),
            sportKey: "tennis_wta_us_open",
            eventStatus: "live",
            commenceTime: Self.commence
        )
        XCTAssertTrue(chartSpeaks, "the chart has a projected series and tennis owes the sentence")
        XCTAssertEqual(
            sentencesOnScreen(chartSpeaks: chartSpeaks, vocab: tennis, isLive: true, isDone: false), 1,
            "#4982: the US Open semi printed this admission twice, a screen-third apart"
        )
    }

    /// The control, and the reason the test above is not vacuous: with nothing
    /// said above it, the map still speaks. If a future edit made
    /// `mapUnitMismatchNote` return nil unconditionally, the count test would
    /// still pass and this one would not.
    func testTheMapStillSpeaksWhenNothingWasSaidAboveIt() {
        let note = MarketMapRail.mapUnitMismatchNote(
            vocab: tennis, statedAbove: false, isLive: true, isDone: false, mapWithheldATile: true
        )
        XCTAssertEqual(
            note, "The scoreboard reports sets, this market quotes games — we do not hold the games played yet."
        )
        XCTAssertEqual(sentencesOnScreen(chartSpeaks: false, vocab: tennis, isLive: true, isDone: false), 1)
    }

    // MARK: - The chart is not always the one that speaks

    /// #4982's one real hazard. `ScoreDifferentialChartView` returns `EmptyView`
    /// when it has no series, so "the chart is in the view tree" is NOT "the
    /// chart said something". Suppressing the map on a chart that never spoke
    /// would print zero explanations for a tile the map really did withhold,
    /// which is #3503's orphan by a new route.
    func testTheAbsenceIsNotClaimedWithoutASeries() throws {
        let chartSpeaks = ScoreDifferentialChartView.statesPlayedCountAbsence(
            history: try history(count: 0),
            sportKey: "tennis_wta_us_open",
            eventStatus: "live",
            commenceTime: Self.commence
        )
        XCTAssertFalse(chartSpeaks, "no projected points means the chart draws nothing and says nothing")
        XCTAssertEqual(
            sentencesOnScreen(chartSpeaks: chartSpeaks, vocab: tennis, isLive: true, isDone: false), 1,
            "the map must be the one that speaks — never zero"
        )
    }

    /// The same hazard reached through the start filter rather than an empty
    /// payload: `buildDataPoints` drops projected points from before the first
    /// ball once the match is under way, so a history made entirely of them
    /// draws an empty chart.
    ///
    /// Both halves hold the status fixed at `live` and vary ONLY the offset, so
    /// what is isolated here is the filter and not the status gate below.
    func testPointsBeforeTheFirstBallDoNotCountAsASeries() throws {
        XCTAssertFalse(
            ScoreDifferentialChartView.statesPlayedCountAbsence(
                history: try history(count: 8, offsetMinutes: -120),
                sportKey: "tennis_wta_us_open",
                eventStatus: "live", commenceTime: Self.commence
            ),
            "every point predates the start, so the live chart has nothing to draw"
        )
        XCTAssertTrue(
            ScoreDifferentialChartView.statesPlayedCountAbsence(
                history: try history(count: 8, offsetMinutes: 1),
                sportKey: "tennis_wta_us_open",
                eventStatus: "live", commenceTime: Self.commence
            ),
            "the identical payload one minute the other side of the first ball does draw"
        )
    }

    /// The status gate, which lives in the predicate rather than beside the
    /// call. `EventDetailView` draws the differential chart only once a match is
    /// live or over, so on a scheduled page the map is always the card that
    /// speaks — even though the payload would otherwise have drawn a series.
    func testAScheduledPageDrawsNoChartSoItCannotHaveSpoken() throws {
        let chartSpeaks = ScoreDifferentialChartView.statesPlayedCountAbsence(
            history: try history(count: 12),
            sportKey: "tennis_wta_us_open",
            eventStatus: "scheduled",
            commenceTime: Self.commence
        )
        XCTAssertFalse(chartSpeaks)
        // ...and the map owes nothing either, because #3465 withholds the
        // sentence until the match is under way. A scheduled page is the one
        // place the honest answer is zero.
        XCTAssertEqual(
            sentencesOnScreen(chartSpeaks: chartSpeaks, vocab: tennis, isLive: false, isDone: false), 0
        )
    }

    // MARK: - The gates that did not move

    /// #3465 — the sentence is tensed, and the arbitration has to be too: a
    /// finished match owes the PAST-tense pair, and it owes it once.
    func testSettledMeansSettledOnBothHalves() throws {
        let chartSpeaks = ScoreDifferentialChartView.statesPlayedCountAbsence(
            history: try history(count: 12),
            sportKey: "tennis_wta_us_open",
            eventStatus: "completed",
            commenceTime: Self.commence
        )
        XCTAssertTrue(chartSpeaks)
        XCTAssertEqual(
            sentencesOnScreen(chartSpeaks: chartSpeaks, vocab: tennis, isLive: false, isDone: true), 1
        )
        // And when the map IS the one speaking, it speaks in the past tense.
        let note = MarketMapRail.mapUnitMismatchNote(
            vocab: tennis, statedAbove: false, isLive: false, isDone: true, mapWithheldATile: true
        )
        XCTAssertEqual(
            note, "The scoreboard reported sets, this market quoted games — we did not hold the games played."
        )
    }

    /// A sport whose scoreboard counts the unit its markets quote owes NEITHER
    /// sentence. Baseball is the case that must not acquire one.
    func testASportThatCountsItsOwnUnitOwesNothing() throws {
        let chartSpeaks = ScoreDifferentialChartView.statesPlayedCountAbsence(
            history: try history(count: 12),
            sportKey: "baseball_mlb",
            eventStatus: "live",
            commenceTime: Self.commence
        )
        XCTAssertFalse(chartSpeaks)
        XCTAssertEqual(
            sentencesOnScreen(chartSpeaks: chartSpeaks, vocab: baseball, isLive: true, isDone: false), 0
        )
    }

    /// #3465 again, from the other side: before the match is under way neither
    /// card owes the sentence, so suppression must not invent one.
    func testNothingIsOwedBeforeTheMatchIsUnderWay() {
        XCTAssertNil(
            MarketMapRail.mapUnitMismatchNote(
                vocab: tennis, statedAbove: false, isLive: false, isDone: false, mapWithheldATile: true
            )
        )
    }

    /// #3509 / #3533 — owed only where a map on screen actually withheld a tile.
    /// Unchanged by #4982, asserted here so the lift into `MarketMapRail` cannot
    /// have dropped it.
    func testAMapThatWithheldNothingSaysNothing() {
        XCTAssertNil(
            MarketMapRail.mapUnitMismatchNote(
                vocab: tennis, statedAbove: false, isLive: true, isDone: false, mapWithheldATile: false
            )
        )
    }

    /// The page-level guard stated over every combination that can reach it:
    /// never two, and never zero where a sentence is owed.
    func testAtMostOneAndNeverZeroAcrossEveryCombination() {
        for chartSpeaks in [true, false] {
            for isDone in [true, false] {
                let isLive = !isDone
                let count = sentencesOnScreen(
                    chartSpeaks: chartSpeaks, vocab: tennis, isLive: isLive, isDone: isDone
                )
                XCTAssertEqual(count, 1, "chartSpeaks=\(chartSpeaks) isDone=\(isDone)")
            }
        }
    }
}
