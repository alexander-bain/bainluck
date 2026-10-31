import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey adapter, part two (the two-team win-probability
/// history), on REAL served bodies decoded exactly as the app decodes them
/// (`APIClient`: `JSONDecoder` with `.convertFromSnakeCase`, no date strategy).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///
/// - `wildBruinsDetail` — `atlas-v6/raw/nhl-15169793-detail.json`, BYTE FOR BYTE
///   (sha256 a11c662df1fd7c94c080cf0c7455c6771da9f8f38de3a44517a0a633f03ea348;
///   the first test re-hashes it). Minnesota Wild 4–1 Boston Bruins, completed.
/// - `wildBruinsHistory` — a REDUCED VERBATIM SUBSET of
///   `atlas-v6/raw/nhl-15169793-history.json` (1,335,078 bytes, sha256
///   cba7c334e453ea653530b0e8c3bde4bb612835019e08ef3dc320e0901a887525, captured
///   2026-10-11). Every top-level key, in source order, is the source's bytes,
///   except (0-based element indexes kept, in source order, one per line):
///     `history`            38 of 494: 313–316, 372–391, 480–493
///     `bookmaker_history`  emptied to {}
///     `espn_history`       5 of 121: 0, 39, 80, 119, 120
///     `win_prob_history`   polymarket 0, 1530–1532 of 1533; kalshi 0, 868–870
///                          of 871; stat_model 0, 1, 102–104 of 105
///     `period_markers`     5 of 104: 0, 35, 36, 70, 71
///     `aggregate_line`     67 of 2535: 1893–1899, 2081–2084, 2355–2385, 2419,
///                          2443–2447, 2465–2469, 2495–2499, 2526–2534
/// - `devilsKnightsDetail` — `shipping-adoption-20261027/cli-candidate-20261030/
///   retained-payloads/nhl-15338496-detail-20261030T201355Z.json`, BYTE FOR BYTE
///   (sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da).
///   New Jersey Devils at Vegas Golden Knights, scheduled 22:00Z.
/// - `devilsKnightsHistory` — a REDUCED VERBATIM SUBSET of the same directory's
///   `nhl-15338496-history-20261030T201355Z.json` (430,695 bytes, sha256
///   0fe7e8cd334d2b32b5d808bd2dbdec974bef052a53775991b1457bd37fafe812), except:
///     `history`            9 of 62: 5–8, 57–61
///     `bookmaker_history`  emptied to {}
///     `win_prob_history`   polymarket 0, 984 of 985; kalshi 0, 551 of 552
///     `aggregate_line`     26 of 1103: 54–62, 513–521, 1095–1102
///
/// Generated and checked by `/tmp/cli-10868-h2/make_subsets.py` (kept outside the
/// repo): every kept element is a verbatim substring of its source, and the
/// parsed subset equals the selected source elements key by key.
///
/// WHAT A SUBSET CHANGES. Rows left out are absent, so an in-game interval
/// across them is wider than served and the chart's own rule breaks there: the
/// in-game runs below are runs OF THE SUBSET. Pre-match intervals are never
/// judged (production), so the before frame is one run even across rows this
/// subset leaves out — rows the full body holds. The blocks that carry a
/// boundary claim are kept whole: 23:44–00:19 around the start, and 02:43
/// through the settlement row at the end.
///
/// CONSTRUCTED here, and named where used: the reader's calendar (Pacific,
/// en_US), `now`, a live replay of the finished game at 01:45:25Z, a
/// sportsbooks-only variant (two keys removed), a draw-priced sport key,
/// three unconfirmed-start variants (one key changed each) and an unconfirmed
/// start with its line rows emptied. Clock words are compared with the adapter's
/// own clock words, never with hard-coded strings.
@MainActor
final class HockeyJourneyHistoryAdapter10868Tests: XCTestCase {
    private typealias H = HockeyJourneyHistoryAdapter10868
    private typealias A = HockeyJourneyPageAdapter10868

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    private func readerHost(_ now: String) -> H.Host {
        H.Host(now: now.asDate!, calendar: Self.pacific, locale: Locale(identifier: "en_US"))
    }

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    private func response(_ json: String) throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// A served body with keys removed or replaced: CONSTRUCTED.
    private func edited(_ json: String, removing: [String] = [], setting: [String: Any] = [:]) throws -> Data {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for key in removing { object.removeValue(forKey: key) }
        for (key, value) in setting { object[key] = value }
        return try JSONSerialization.data(withJSONObject: object)
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    /// Each run's first and last time.
    private func bounds(_ series: FieldHistorySeries10868) -> [[Double]] {
        series.runs.map { [$0.points.first?.x ?? .nan, $0.points.last?.x ?? .nan] }
    }

    /// The served timestamp a point id names.
    private func stamp(_ pointID: String) -> String {
        String(pointID[pointID.index(after: pointID.firstIndex(of: "#")!)...])
    }

    // MARK: - Fixtures

    func testTheEmbeddedDetailsAreTheRetainedBytesAndTheSubsetsDecode() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(sha256(Self.wildBruinsDetail), "a11c662df1fd7c94c080cf0c7455c6771da9f8f38de3a44517a0a633f03ea348")
        XCTAssertEqual(sha256(Self.devilsKnightsDetail), "50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da")

        let finished = try response(Self.wildBruinsHistory)
        XCTAssertEqual(finished.eventId, 15169793)
        XCTAssertEqual(finished.status, "completed")
        XCTAssertEqual(finished.aggregateLine?.count, 67)
        XCTAssertEqual(finished.history.count, 38)
        XCTAssertEqual(finished.commenceTimeIsKickoff, true)
        XCTAssertEqual(finished.evidenceContract?.readableResolution, 300)
        XCTAssertTrue(try XCTUnwrap(finished.aggregateLine).allSatisfy { $0.awayProbability == nil },
                      "the served blend is home-only: the away trace is the complement, labelled as such")
        XCTAssertEqual(H.line(finished), .blend)

        let before = try response(Self.devilsKnightsHistory)
        XCTAssertEqual(before.eventId, 15338496)
        XCTAssertEqual(before.blendEdgePinned, true)
        XCTAssertEqual(before.aggregateLine?.count, 26)
        XCTAssertEqual(H.line(before), .blend)
    }

    // MARK: - Final

    func testTheFinalDrawsTheBlendFromTheLastPregameRowToTheGamesEndAndNeverTheSettlement() throws {
        let event = try detail(Self.wildBruinsDetail)
        let history = try response(Self.wildBruinsHistory)
        let host = readerHost("2026-10-11T04:56:41Z")
        let input = H.history(history, event: event, phase: .final, host: host)
        let home = input.series[0]
        XCTAssertEqual(home.id, "blend:15169793:home")
        XCTAssertEqual(home.name, "Minnesota Wild")
        XCTAssertEqual(home.shape, .circle)
        let points = home.runs.flatMap(\.points)

        // The server appends the result LAST: 02:48 at 1.0, after a 03:14 row.
        let settlement = try XCTUnwrap(history.aggregateLine?.last)
        XCTAssertEqual(settlement.timestamp, "2026-10-04T02:48:00+00:00")
        XCTAssertEqual(settlement.homeProbability, 1.0)
        XCTAssertFalse(points.contains { $0.probability == 1.0 }, "the result is never drawn as a reading")

        // The game ends where the chart clips it; the 03:14 row is after the game.
        let end = try XCTUnwrap(OddsChartView.gameEndDate(status: event.status, history: history))
        XCTAssertEqual(end, "2026-10-04T02:50:00Z".asDate)
        XCTAssertTrue(points.allSatisfy { $0.x <= end.timeIntervalSince1970 })
        XCTAssertFalse(points.contains { $0.x == x("2026-10-04T03:14:00+00:00") })

        let pregame = "2026-10-03T23:59:00+00:00"
        XCTAssertEqual(points.first?.x, x(pregame))
        XCTAssertEqual(points.first?.probability, 0.66)
        XCTAssertEqual(points.first?.style, .hollow)
        XCTAssertEqual(points.filter { $0.style == .hollow }.count, 1, "only the last pregame row is hollow")
        XCTAssertEqual(points.last?.x, x("2026-10-04T02:49:00+00:00"))
        XCTAssertEqual(points.last?.probability, 0.98857)
        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x(pregame), upper: x("2026-10-04T02:49:00+00:00")))

        XCTAssertEqual(input.readout, .singleBefore(label: "Pregame"))
        XCTAssertEqual(home.before, .observation(
            pointID: H.pointID(home.id, pregame), figure: "66%",
            provenance: "Last pregame · \(A.clockWords(pregame.asDate!, host: host.words))"))
        XCTAssertEqual(home.recorded, .absent(words: "Not recorded"))
        XCTAssertEqual(input.caption, "Game history")
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: "Hollow · last pregame", filled: nil))
        XCTAssertEqual(input.details?.id, "history.details")
        XCTAssertEqual(input.expand?.id, "history.expand")
        XCTAssertNil(input.inspect)
        XCTAssertNil(input.plotAbsence)
    }

    func testInGameOmittedSpansStartNewRunsAndARunHoldsOnlyNeighbouringServedRows() throws {
        let history = try response(Self.wildBruinsHistory)
        let input = H.history(history, event: try detail(Self.wildBruinsDetail), phase: .final,
                              host: readerHost("2026-10-11T04:56:41Z"))
        let home = input.series[0]
        XCTAssertEqual(bounds(home), [
            ["2026-10-03T23:59:00+00:00", "2026-10-04T00:19:00+00:00"],
            ["2026-10-04T00:53:00+00:00", "2026-10-04T00:53:00+00:00"],
            ["2026-10-04T01:20:00+00:00", "2026-10-04T01:24:00+00:00"],
            ["2026-10-04T01:42:00+00:00", "2026-10-04T01:46:00+00:00"],
            ["2026-10-04T02:12:00+00:00", "2026-10-04T02:16:00+00:00"],
            ["2026-10-04T02:43:00+00:00", "2026-10-04T02:49:00+00:00"],
        ].map { $0.map(x) })
        XCTAssertEqual(home.runs.map(\.points.count), [19, 1, 5, 5, 5, 7], "a lone row is a mark, never dropped")

        // Inside a run, neighbours are neighbours in the served body: nothing left out is crossed.
        let served = try XCTUnwrap(history.aggregateLine).map(\.timestamp)
        for run in home.runs {
            let positions = try run.points.map { try XCTUnwrap(served.firstIndex(of: stamp($0.id))) }
            XCTAssertEqual(positions, Array(positions[0]...positions[positions.count - 1]))
        }
    }

    func testOnATwoOutcomeSportTheAwayTraceIsTheOtherSideOfTheSameBlendRowForRow() throws {
        let event = try detail(Self.wildBruinsDetail)
        let history = try response(Self.wildBruinsHistory)
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw(event.sport), "a hockey winner market has two outcomes")
        let note = "Boston Bruins is the other side of the same blend: 100% − Minnesota Wild."
        for (phase, now) in [(HockeyJourneyPagePhase10868.final, "2026-10-11T04:56:41Z"),
                             (.live, "2026-10-04T01:45:25Z")] {
            let host = readerHost(now)
            let input = H.history(history, event: event, phase: phase, host: host)
            let home = input.series[0], away = input.series[1]
            XCTAssertEqual(away.id, "blend:15169793:away")
            XCTAssertEqual(away.name, "Boston Bruins")
            XCTAssertEqual(away.shape, .square)

            // The same rows, the same breaks: run for run, point for point, at the same x.
            XCTAssertEqual(bounds(away), bounds(home))
            XCTAssertEqual(away.runs.map(\.points.count), home.runs.map(\.points.count))
            let homePoints = home.runs.flatMap(\.points), awayPoints = away.runs.flatMap(\.points)
            XCTAssertEqual(awayPoints.count, homePoints.count)
            for (h, a) in zip(homePoints, awayPoints) {
                XCTAssertEqual(a.x, h.x)
                XCTAssertEqual(stamp(a.id), stamp(h.id))
                XCTAssertEqual(a.style, h.style)
                // The served blend has no away value, so this is the documented complement of that row.
                XCTAssertEqual(a.probability, 1 - h.probability)
                XCTAssertEqual(a.probability, DrawPricedWinner.printablePair(
                    away: 1 - h.probability, home: h.probability, sport: event.sport)?.away)
            }
            // Nothing the home trace removed returns as its other side.
            XCTAssertFalse(awayPoints.contains { $0.probability == 0.0 }, "the settlement's other side is not drawn")
            XCTAssertFalse(awayPoints.contains { $0.x == x("2026-10-04T03:14:00+00:00") })

            XCTAssertEqual(input.notes, ["Source: Bain Luck", note, "Gaps remain blank."])
            XCTAssertEqual(input.summary,
                           "Minnesota Wild and Boston Bruins win probability, recorded observations only. " + note)

            // Its readings follow its own points; one instant is one two-sided decision.
            let pregame = "2026-10-03T23:59:00+00:00"
            let pregamePair = duelProbabilityStrings(away: 1 - 0.66, home: 0.66, complementaryAway: true)
            XCTAssertEqual(away.before, .observation(
                pointID: H.pointID(away.id, pregame), figure: pregamePair.away,
                provenance: "Last pregame · \(A.clockWords(pregame.asDate!, host: host.words))"))
            XCTAssertEqual(home.before, .observation(
                pointID: H.pointID(home.id, pregame), figure: pregamePair.home,
                provenance: "Last pregame · \(A.clockWords(pregame.asDate!, host: host.words))"))
            if phase == .live {
                let latest = "2026-10-04T01:45:00+00:00"
                let latestPair = duelProbabilityStrings(away: 1 - 0.81574, home: 0.81574, complementaryAway: true)
                XCTAssertEqual(away.recorded, .observation(
                    pointID: H.pointID(away.id, latest), figure: latestPair.away,
                    provenance: "Recorded \(A.clockWords(latest.asDate!, host: host.words))"))
            } else {
                XCTAssertEqual(away.recorded, .absent(words: "Not recorded"))
            }
        }
    }

    /// CONSTRUCTED: the same retained detail with `sport` set to a draw-priced key.
    func testOnASportThatPricesADrawTheAwaySeriesIsAbsentNotAComplement() throws {
        let event = try decoder().decode(EventDetail.self, from: edited(
            Self.wildBruinsDetail, setting: ["sport": "soccer_epl"]))
        XCTAssertTrue(DrawPricedWinner.sportPricesADraw(event.sport))
        let input = H.history(try response(Self.wildBruinsHistory), event: event, phase: .final,
                              host: readerHost("2026-10-11T04:56:41Z"))
        let away = input.series[1]
        XCTAssertFalse(input.series[0].runs.isEmpty, "the home trace still draws")
        XCTAssertTrue(away.runs.isEmpty, "where a draw is priced, 1 − home is \"home does not win\", not the away side")
        XCTAssertEqual(away.absentWords, "No recorded history")
        XCTAssertEqual(away.before, .absent(words: "Not recorded"))
        XCTAssertEqual(input.notes, ["Source: Bain Luck", "Gaps remain blank."])
        XCTAssertEqual(input.summary,
                       "Minnesota Wild win probability, recorded observations only. No recorded history for Boston Bruins.")
    }

    /// CONSTRUCTED: the same retained body without `win_prob_history` and
    /// `aggregate_line` — the sportsbooks-only shape, where the chart's line is
    /// the consensus and each row serves both teams.
    func testWhereTheLineServesAwayValuesTheAwaySeriesIsThoseValuesAndAnUnpricedRowBreaksTheRun() throws {
        let event = try detail(Self.wildBruinsDetail)
        let history = try decoder().decode(EventHistoryResponse.self, from: edited(
            Self.wildBruinsHistory, removing: ["win_prob_history", "aggregate_line"]))
        XCTAssertEqual(H.line(history), .consensus)
        let host = readerHost("2026-10-11T04:56:41Z")
        let input = H.history(history, event: event, phase: .final, host: host)
        let home = input.series[0], away = input.series[1]
        XCTAssertEqual(home.id, "consensus:15169793:home")
        XCTAssertEqual(input.notes.first, "Source: Sportsbook Consensus (market)")

        let expected = [
            ["2026-10-03T23:46:00+00:00", "2026-10-04T00:25:00+00:00"],
            ["2026-10-04T02:32:00+00:00", "2026-10-04T02:38:00+00:00"],
            ["2026-10-04T02:41:00+00:00", "2026-10-04T02:41:00+00:00"],
            ["2026-10-04T02:43:00+00:00", "2026-10-04T02:45:00+00:00"],
        ].map { $0.map(x) }
        XCTAssertEqual(bounds(home), expected)
        XCTAssertEqual(bounds(away), expected)

        // The away point is the served away value, not one minus home.
        let row = try XCTUnwrap(history.history.first { $0.timestamp == "2026-10-04T02:36:00+00:00" })
        XCTAssertEqual(row.homeProbability, 0.9687)
        XCTAssertEqual(row.awayProbability, 0.0314)
        let drawn = try XCTUnwrap(away.runs.flatMap(\.points).first { $0.x == x("2026-10-04T02:36:00+00:00") })
        XCTAssertEqual(drawn.probability, 0.0314)
        XCTAssertNotEqual(drawn.probability, 1 - 0.9687)

        // Rows priced by no sportsbook break the line and draw nothing; the last is the result.
        for stamp in ["2026-10-04T02:39:00+00:00", "2026-10-04T02:42:00+00:00",
                      "2026-10-04T02:46:00+00:00", "2026-10-04T02:48:00+00:00"] {
            XCTAssertEqual(history.history.first { $0.timestamp == stamp }?.bookmakerCount, 0)
            XCTAssertFalse((home.runs + away.runs).flatMap(\.points).contains { $0.x == x(stamp) }, stamp)
        }

        let pregame = "2026-10-03T23:46:00+00:00"
        let clock = A.clockWords(pregame.asDate!, host: host.words)
        XCTAssertEqual(home.before, .observation(pointID: H.pointID(home.id, pregame), figure: "66%",
                                                 provenance: "Last pregame · \(clock)"))
        XCTAssertEqual(away.before, .observation(pointID: H.pointID(away.id, pregame), figure: "34%",
                                                 provenance: "Last pregame · \(clock)"))
        XCTAssertEqual(input.summary, "Minnesota Wild and Boston Bruins win probability, recorded observations only.")
    }

    // MARK: - Live

    /// CONSTRUCTED: the finished game replayed at 01:45:25Z (late second period).
    func testALiveFrameEndsAtTheLastRowAtOrBeforeNowWithGuidesAtOrBeforeIt() throws {
        let history = try response(Self.wildBruinsHistory)
        let host = readerHost("2026-10-04T01:45:25Z")
        let input = H.history(history, event: try detail(Self.wildBruinsDetail), phase: .live, host: host)
        let home = input.series[0]
        XCTAssertEqual(bounds(home), [
            ["2026-10-03T23:59:00+00:00", "2026-10-04T00:19:00+00:00"],
            ["2026-10-04T00:53:00+00:00", "2026-10-04T00:53:00+00:00"],
            ["2026-10-04T01:20:00+00:00", "2026-10-04T01:24:00+00:00"],
            ["2026-10-04T01:42:00+00:00", "2026-10-04T01:45:00+00:00"],
        ].map { $0.map(x) })
        XCTAssertTrue(home.runs.flatMap(\.points).allSatisfy { $0.x <= host.now.timeIntervalSince1970 })
        XCTAssertEqual(input.domain.upper, x("2026-10-04T01:45:00+00:00"), "the frame ends at the last row, never at now")

        // First sightings of each period, from ESPN's own rows; P3 comes later.
        XCTAssertEqual(input.guides.map(\.label), ["P1", "P2"])
        XCTAssertEqual(input.guides.map(\.x), [x("2026-10-04T00:14:57.965570+00:00"), x("2026-10-04T01:10:59.081904+00:00")])
        XCTAssertTrue(input.guides.allSatisfy { $0.x >= input.domain.lower && $0.x <= input.domain.upper })

        XCTAssertEqual(input.readout, .beforeAndRecorded(beforeLabel: "Pregame", recordedLabel: "Recorded"))
        let latest = "2026-10-04T01:45:00+00:00"
        XCTAssertEqual(home.recorded, .observation(
            pointID: H.pointID(home.id, latest), figure: "82%",
            provenance: "Recorded \(A.clockWords(latest.asDate!, host: host.words))"))
        XCTAssertEqual(input.inspect?.id, "history.inspect")
        // Only the full-size reader has an owner yet: details and inspection are offered, unavailable.
        XCTAssertEqual(input.expand?.isAvailable, true)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.inspect?.isAvailable, false)
        XCTAssertEqual(input.caption, "Game history")
        XCTAssertNil(input.inspection, "the held inspection is the host's")
    }

    func testTheFinalGuidesAreThePeriodStartsAndNeverTheResultOrAnUnservedGoal() throws {
        let history = try response(Self.wildBruinsHistory)
        let input = H.history(history, event: try detail(Self.wildBruinsDetail), phase: .final,
                              host: readerHost("2026-10-11T04:56:41Z"))
        XCTAssertEqual(input.guides.map(\.label), ["P1", "P2", "P3"])
        XCTAssertEqual(input.guides.map(\.id), ["period:P1", "period:P2", "period:P3"])
        XCTAssertEqual(input.guides.last?.x, x("2026-10-04T02:08:56.957013+00:00"))
        XCTAssertTrue(input.guides.allSatisfy { $0.x <= input.domain.upper })
        // ESPN serves a `Final` row at 02:48, inside the frame: a result, not a period start.
        XCTAssertTrue(try XCTUnwrap(history.espnHistory).contains { $0.period == "Final" })
        XCTAssertEqual(history.scoringPlays, [], "this body serves no scoring plays, so no goal guide is drawn")
    }

    // MARK: - Before

    func testBeforeTheStartTheFrameIsThePregameDayEndingAtTheLastRecordedRowNotThePin() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let history = try response(Self.devilsKnightsHistory)
        let host = readerHost("2026-10-30T20:13:55Z")
        XCTAssertEqual(A.phase(event, now: host.now), .before)
        let input = H.history(history, event: event, phase: .before, host: host)
        let home = input.series[0]
        let points = home.runs.flatMap(\.points)

        // The day reaches back from the last pregame reading (20:11), not from the listed start
        // (22:00): the subset's 21:58 and 21:59 the day before are recorded readings inside it.
        let floor = x("2026-10-30T20:11:00+00:00") - H.beforeWindow
        XCTAssertEqual(points.first?.x, x("2026-10-29T21:58:00+00:00"), "the last pregame reading less one day, inclusive")
        XCTAssertFalse(points.contains { $0.x < floor })
        let pin = try XCTUnwrap(history.aggregateLine?.last)
        XCTAssertEqual(pin.timestamp, "2026-10-30T20:12:00+00:00")
        XCTAssertFalse(points.contains { $0.x == x(pin.timestamp) }, "the pinned edge is the hero's, not a recorded row")
        let lastPregame = "2026-10-30T20:11:00+00:00"
        XCTAssertEqual(points.last?.x, x(lastPregame))
        XCTAssertEqual(points.last?.style, .hollow)
        XCTAssertEqual(points.count, 25)
        XCTAssertEqual(home.runs.count, 1,
                       "the chart never breaks a pre-match interval (OddsChartView.observationSegments); "
                       + "the full body holds the rows this subset leaves out")

        // 0.505 against its complement is one two-sided decision, never 51% beside 50%.
        let pair = duelProbabilityStrings(away: 1 - 0.505, home: 0.505, complementaryAway: true)
        XCTAssertEqual(home.before, .observation(
            pointID: H.pointID(home.id, lastPregame), figure: pair.home,
            provenance: "Last pregame · \(A.clockWords(lastPregame.asDate!, host: host.words))"))
        XCTAssertEqual(home.recorded, .absent(words: "Not recorded"))
        let away = input.series[1]
        let awayPoints = away.runs.flatMap(\.points)
        XCTAssertEqual(awayPoints.map(\.x), points.map(\.x), "the other side of the same blend, row for row")
        XCTAssertEqual(awayPoints.map(\.probability), points.map { 1 - $0.probability })
        XCTAssertEqual(away.runs.count, home.runs.count)
        XCTAssertEqual(away.before, .observation(
            pointID: H.pointID(away.id, lastPregame), figure: pair.away,
            provenance: "Last pregame · \(A.clockWords(lastPregame.asDate!, host: host.words))"))
        XCTAssertTrue(input.notes.contains("New Jersey Devils is the other side of the same blend: 100% − Vegas Golden Knights."))
        XCTAssertEqual(input.guides, [])
        XCTAssertEqual(input.caption, "Before game")
        XCTAssertEqual(input.readout, .singleBefore(label: "Pregame"))
        XCTAssertNil(input.inspect)

        // Ticks: the chart's own plan, in the reader's calendar, zone and locale.
        let domain = Date(timeIntervalSince1970: input.domain.lower)...Date(timeIntervalSince1970: input.domain.upper)
        let plan = OddsChartView.xAxisPlan(for: domain, calendar: Self.pacific)
        XCTAssertEqual(plan.labelStyle, .dayAndHour, "a frame across two of the reader's days names the day")
        let ticks = OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: Self.pacific)
        XCTAssertFalse(ticks.isEmpty)
        XCTAssertEqual(input.xTicks.map(\.value), ticks.map(\.timeIntervalSince1970))
        let style = Date.FormatStyle(locale: Locale(identifier: "en_US"), calendar: Self.pacific,
                                     timeZone: Self.pacific.timeZone).weekday(.abbreviated).hour()
        XCTAssertEqual(input.xTicks.map(\.lines), ticks.map { [$0.formatted(style)] })
        for tick in input.xTicks {
            XCTAssertEqual(Self.pacific.component(.minute, from: Date(timeIntervalSince1970: tick.value)), 0)
            XCTAssertTrue(input.domain.contains(tick.value))
        }
        XCTAssertEqual(input.yTicks, [FieldHistoryTick10868(value: 0, lines: ["0%"]),
                                      FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                                      FieldHistoryTick10868(value: 1, lines: ["100%"])])
    }

    /// CONSTRUCTED: one key changed on each served body — the scheduled game's
    /// history with `commence_time_is_kickoff: false`, its detail with
    /// `start_is_tbd: true`, and the finished game's history with
    /// `commence_time_is_kickoff: false`. An uncertain start withholds the
    /// pregame/game split, never the recorded readings.
    func testAStartThatIsNotAConfirmedKickoffStillDrawsTheRecordedReadingsUnsplit() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let history = try response(Self.devilsKnightsHistory)
        let notKickoff = try decoder().decode(EventHistoryResponse.self, from: edited(
            Self.devilsKnightsHistory, setting: ["commence_time_is_kickoff": false]))
        let placeholder = try decoder().decode(EventDetail.self, from: edited(
            Self.devilsKnightsDetail, setting: ["start_is_tbd": true]))
        let why = "Pregame and game readings are split at a confirmed start, and this game has none yet."
        for (body, game) in [(notKickoff, event), (history, placeholder)] {
            let input = H.history(body, event: game, phase: .before, host: readerHost("2026-10-30T20:13:55Z"))
            XCTAssertNil(input.plotAbsence, "the recorded readings are not blanked")
            let home = input.series[0], away = input.series[1]
            let points = home.runs.flatMap(\.points)

            // Every served blend row but the pinned edge (26 − 1), from the first served
            // row: there is no listed start to reach back one day from.
            XCTAssertEqual(points.count, 25)
            XCTAssertEqual(home.runs.count, 1)
            XCTAssertEqual(points.first?.x, x("2026-10-29T21:58:00+00:00"))
            XCTAssertEqual(points.first?.probability, 0.515)
            XCTAssertEqual(points.last?.x, x("2026-10-30T20:11:00+00:00"))
            XCTAssertEqual(points.last?.probability, 0.505)
            XCTAssertFalse(points.contains { $0.x == x("2026-10-30T20:12:00+00:00") }, "the pinned edge is still not a reading")
            XCTAssertEqual(away.runs.flatMap(\.points).map(\.x), points.map(\.x))
            XCTAssertEqual(away.runs.flatMap(\.points).map(\.probability), points.map { 1 - $0.probability })
            XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x("2026-10-29T21:58:00+00:00"),
                                                                upper: x("2026-10-30T20:11:00+00:00")))

            // No reading is called pregame: no hollow mark, no baseline readout; the slot says why.
            XCTAssertTrue((home.runs + away.runs).flatMap(\.points).allSatisfy { $0.style == .filled })
            XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
            XCTAssertEqual(input.readout, .singleBefore(label: "Start time not confirmed"))
            XCTAssertEqual(home.before, .absent(words: why))
            XCTAssertEqual(away.before, .absent(words: why))
            XCTAssertEqual(input.guides, [])

            // Labelled by time: the chart's own ticks over the drawn frame.
            let domain = Date(timeIntervalSince1970: input.domain.lower)...Date(timeIntervalSince1970: input.domain.upper)
            let ticks = OddsChartView.xAxisTicks(
                for: domain, plan: OddsChartView.xAxisPlan(for: domain, calendar: Self.pacific), calendar: Self.pacific)
            XCTAssertFalse(ticks.isEmpty)
            XCTAssertEqual(input.xTicks.map(\.value), ticks.map(\.timeIntervalSince1970))
        }

        // The finished game: confirmed, its frame carries P1–P3 guides and a hollow
        // last pregame row (the Final tests above); unconfirmed, neither.
        let finished = try decoder().decode(EventHistoryResponse.self, from: edited(
            Self.wildBruinsHistory, setting: ["commence_time_is_kickoff": false]))
        let input = H.history(finished, event: try detail(Self.wildBruinsDetail), phase: .final,
                              host: readerHost("2026-10-11T04:56:41Z"))
        let home = input.series[0]
        let points = home.runs.flatMap(\.points)
        // 67 served rows, less the settlement row and the 03:14 row after the game's end.
        XCTAssertEqual(points.count, 65)
        XCTAssertEqual(points.first?.x, x("2026-10-02T23:52:00+00:00"))
        XCTAssertEqual(points.first?.probability, 0.645)
        XCTAssertEqual(points.last?.x, x("2026-10-04T02:49:00+00:00"))
        XCTAssertEqual(points.last?.probability, 0.98857)
        XCTAssertFalse(points.contains { $0.probability == 1.0 }, "the result is still never a reading")
        XCTAssertTrue(points.allSatisfy { $0.style == .filled })
        XCTAssertEqual(input.guides, [], "no period or scoring guide without a confirmed start")
        XCTAssertEqual(input.readout, .singleBefore(label: "Start time not confirmed"))
        XCTAssertEqual(home.before, .absent(words: why))
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
    }

    /// CONSTRUCTED: the scheduled game's history with `commence_time_is_kickoff:
    /// false` and both line arrays (`aggregate_line`, `history`) emptied.
    func testAnUnconfirmedStartWithNoRecordedRowsStillShowsTheEmptyState() throws {
        let empty = try decoder().decode(EventHistoryResponse.self, from: edited(
            Self.devilsKnightsHistory,
            setting: ["commence_time_is_kickoff": false, "aggregate_line": [Any](), "history": [Any]()]))
        let input = H.history(empty, event: try detail(Self.devilsKnightsDetail), phase: .before,
                              host: readerHost("2026-10-30T20:13:55Z"))
        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: "No recorded history", words: nil))
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertEqual(input.xTicks, [])
        XCTAssertEqual(input.guides, [])
        XCTAssertEqual(input.summary, "No recorded history")
        // Details has no destination yet: offered, unavailable. Nothing to expand or inspect.
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertNil(input.expand)
        XCTAssertNil(input.inspect)
    }

    // MARK: - Before: each side's own recorded day (#10868 shared pregame window)

    /// CONSTRUCTED: the scheduled game's body with its consensus `history` replaced and no
    /// venue series, blend or pin, so each team reads its OWN served value and the two can stop
    /// apart. Listed start 22:00Z, a confirmed kick-off.
    private func consensusBody(_ rows: [(String, Double?, Double?)]) throws -> EventHistoryResponse {
        let served: [[String: Any]] = rows.map { row in
            ["timestamp": row.0,
             "home_probability": row.1.map { $0 as Any } ?? NSNull(),
             "away_probability": row.2.map { $0 as Any } ?? NSNull(),
             "bookmaker_count": 5]
        }
        return try decoder().decode(EventHistoryResponse.self, from: edited(
            Self.devilsKnightsHistory,
            setting: ["history": served, "aggregate_line": [Any](), "win_prob_history": [String: Any](),
                      "bookmaker_history": [String: Any](), "blend_edge_pinned": false]))
    }

    private func xs(_ series: FieldHistorySeries10868) -> [Double] { series.runs.flatMap(\.points).map(\.x) }

    func testBeforeTheStartEachSideReadsItsOwnDayAndTheSharedFrameMaySpanMoreThanADay() throws {
        let body = try consensusBody([
            ("2026-10-29T10:00:00Z", 0.6, 0.4),
            ("2026-10-29T12:00:00Z", 0.61, 0.39),
            ("2026-10-30T10:00:00Z", 0.62, 0.38), // the away side's last reading
            ("2026-10-30T11:30:00Z", 0.63, nil), // the home side's last reading; no away value
            ("2026-10-30T21:00:00Z", 0.64, 0.36), // after now: not a reading yet
        ])
        XCTAssertEqual(H.line(body), .consensus)
        let host = readerHost("2026-10-30T20:13:55Z")
        let input = H.history(body, event: try detail(Self.devilsKnightsDetail), phase: .before, host: host)
        let home = input.series[0], away = input.series[1]
        XCTAssertEqual(xs(home), ["2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z", "2026-10-30T11:30:00Z"].map(x))
        XCTAssertEqual(xs(away), ["2026-10-29T10:00:00Z", "2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z"].map(x))
        // Each side ends at its own reading, hollow; neither borrows the other's clock.
        XCTAssertEqual(home.runs.flatMap(\.points).filter { $0.style == .hollow }.map(\.x), [x("2026-10-30T11:30:00Z")])
        XCTAssertEqual(away.runs.flatMap(\.points).filter { $0.style == .hollow }.map(\.x), [x("2026-10-30T10:00:00Z")])
        XCTAssertFalse(xs(away).contains(x("2026-10-30T11:30:00Z")), "the away side never takes the home side's time")
        XCTAssertFalse(xs(home).contains(x("2026-10-29T10:00:00Z")), "outside the home side's own day")
        guard case let .observation(homeID, _, homeWords) = home.before,
              case let .observation(awayID, _, awayWords) = away.before else {
            return XCTFail("each side keeps its own last pregame reading")
        }
        XCTAssertEqual(homeID, H.pointID(home.id, "2026-10-30T11:30:00Z"))
        XCTAssertEqual(awayID, H.pointID(away.id, "2026-10-30T10:00:00Z"))
        XCTAssertEqual(homeWords, "Last pregame · \(A.clockWords("2026-10-30T11:30:00Z".asDate!, host: host.words))")
        XCTAssertEqual(awayWords, "Last pregame · \(A.clockWords("2026-10-30T10:00:00Z".asDate!, host: host.words))")
        // Each side's own window is at most a day; the shared frame is NOT promised to be.
        for series in [home, away] {
            let first = try XCTUnwrap(xs(series).first)
            let last = try XCTUnwrap(xs(series).last)
            XCTAssertLessThanOrEqual(last - first, H.beforeWindow)
        }
        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x("2026-10-29T10:00:00Z"),
                                                            upper: x("2026-10-30T11:30:00Z")))
        XCTAssertGreaterThan(input.domain.upper - input.domain.lower, H.beforeWindow)
        XCTAssertTrue((xs(home) + xs(away)).allSatisfy { $0 <= host.now.timeIntervalSince1970 })
    }

    func testBeforeTheStartTheDayOpensExactlyOneDayBeforeTheLastPregameReadingInclusive() throws {
        let body = try consensusBody([
            ("2026-10-29T14:00:00Z", 0.55, 0.45), // 30 h before the last reading: outside
            ("2026-10-29T19:59:00Z", 0.56, 0.44), // one day and one minute before: outside
            ("2026-10-29T20:00:00Z", 0.57, 0.43), // exactly one day before: inside
            ("2026-10-30T08:00:00Z", 0.58, 0.42),
            ("2026-10-30T20:00:00Z", 0.59, 0.41), // the last pregame reading
        ])
        let input = H.history(body, event: try detail(Self.devilsKnightsDetail), phase: .before,
                              host: readerHost("2026-10-30T20:13:55Z"))
        let expected = ["2026-10-29T20:00:00Z", "2026-10-30T08:00:00Z", "2026-10-30T20:00:00Z"].map(x)
        XCTAssertEqual(xs(input.series[0]), expected)
        XCTAssertEqual(xs(input.series[1]), expected)
        XCTAssertLessThan(expected[0], x("2026-10-30T22:00:00+00:00") - H.beforeWindow,
                          "older than the listed start less one day, and drawn: that start is still in the future")
        XCTAssertEqual(input.series[0].runs.count, 1)
    }

    func testBeforeTheStartASideWithNoPregameReadingDrawsNothingAndTheOtherKeepsItsOwnDay() throws {
        let body = try consensusBody([("2026-10-29T12:00:00Z", 0.61, nil), ("2026-10-30T10:00:00Z", 0.62, nil)])
        let input = H.history(body, event: try detail(Self.devilsKnightsDetail), phase: .before,
                              host: readerHost("2026-10-30T20:13:55Z"))
        XCTAssertEqual(xs(input.series[0]), ["2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z"].map(x))
        XCTAssertTrue(input.series[1].runs.isEmpty)
        XCTAssertEqual(input.series[1].before, .absent(words: "Not recorded"))
        XCTAssertEqual(input.summary, "Vegas Golden Knights win probability, recorded observations only. "
                       + "No recorded history for New Jersey Devils.")
    }

    func testBeforeTheStartWithNoPregameReadingOnEitherSideItIsStillNoRecordedHistory() throws {
        let body = try consensusBody([
            ("2026-10-30T21:00:00Z", 0.64, 0.36), // after now
            ("2026-10-30T22:30:00Z", 0.66, 0.34), // after the start
        ])
        let input = H.history(body, event: try detail(Self.devilsKnightsDetail), phase: .before,
                              host: readerHost("2026-10-30T20:13:55Z"))
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: "No recorded history", words: nil))
    }

    /// CONSTRUCTED: the served body re-serialized, every blend row older than `cut` made
    /// unreadable (home outside 0…1) — the same rows, indexes and clocks, no value. Both sides of
    /// each comparison take this same path, so serialization cannot differ between them.
    private func blankingBlend(_ json: String, before cut: Double?) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        let rows = try XCTUnwrap(object["aggregate_line"] as? [[String: Any]])
        object["aggregate_line"] = rows.map { row -> [String: Any] in
            guard let cut, let stamp = row["timestamp"] as? String, let date = stamp.asDate,
                  date.timeIntervalSince1970 < cut else { return row }
            var blank = row
            blank["home_probability"] = -1.0
            return blank
        }
        return try decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func hollowX(_ input: FieldHistoryInput10868) throws -> Double {
        try XCTUnwrap(input.series[0].runs.flatMap(\.points).first { $0.style == .hollow }?.x)
    }

    func testThePregameWindowNeverReachesTheLiveOrFinalFrames() throws {
        let event = try detail(Self.wildBruinsDetail)
        let whole = try blankingBlend(Self.wildBruinsHistory, before: nil)

        let finalHost = readerHost("2026-10-11T04:56:41Z")
        let finished = H.history(whole, event: event, phase: .final, host: finalHost)
        let finalCut = try hollowX(finished)
        XCTAssertEqual(finalCut, x("2026-10-03T23:59:00+00:00"))
        let finalBlanked = try blankingBlend(Self.wildBruinsHistory, before: finalCut)
        XCTAssertEqual(H.history(finalBlanked, event: event, phase: .final, host: finalHost), finished)

        let liveHost = readerHost("2026-10-04T01:45:25Z")
        let during = H.history(whole, event: event, phase: .live, host: liveHost)
        let liveCut = try hollowX(during)
        let liveBlanked = try blankingBlend(Self.wildBruinsHistory, before: liveCut)
        XCTAssertEqual(H.history(liveBlanked, event: event, phase: .live, host: liveHost), during)

        // Positive control: the same blanking DOES change the before frame, which reads the older rows.
        let knights = try detail(Self.devilsKnightsDetail)
        let beforeHost = readerHost("2026-10-30T20:13:55Z")
        let before = H.history(try blankingBlend(Self.devilsKnightsHistory, before: nil), event: knights,
                               phase: .before, host: beforeHost)
        let beforeCut = try hollowX(before)
        let beforeBlanked = try blankingBlend(Self.devilsKnightsHistory, before: beforeCut)
        let blanked = H.history(beforeBlanked, event: knights, phase: .before, host: beforeHost)
        XCTAssertNotEqual(blanked, before)
        XCTAssertEqual(xs(blanked.series[0]), [beforeCut])
    }

    /// Rams vs Bills (14780558), read 18.5 h before a confirmed kick-off: the readings older than
    /// the start less one day are drawn, up to the last real reading.
    func testAFutureStartNeverShortensTheRecordedDay() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(sha256(Self.ramsDetail), "1f81fa527d56660a7c3fb0b495b0a8489aa7b202a9cc200558c3b817940b0eb9")
        let event = try detail(Self.ramsDetail)
        let history = try response(Self.ramsHistory)
        XCTAssertEqual(history.aggregateLine?.count, 5)
        XCTAssertEqual(H.line(history), .blend)
        let input = H.history(history, event: event, phase: .before, host: readerHost("2026-10-12T05:45:12Z"))
        let home = input.series[0], away = input.series[1]
        let points = home.runs.flatMap(\.points)
        XCTAssertEqual(points.map(\.x), ["2026-10-11T05:45:00+00:00", "2026-10-12T00:14:00+00:00",
                                         "2026-10-12T00:15:00+00:00", "2026-10-12T05:44:00+00:00"].map(x))
        let kickoff = x("2026-10-13T00:15:00+00:00")
        XCTAssertEqual(points.filter { $0.x < kickoff - H.beforeWindow }.count, 2,
                       "the readings a window measured from the future start used to cut off")
        XCTAssertFalse(points.contains { $0.x == x("2026-10-12T05:45:00+00:00") }, "the pinned edge is the hero's, not a reading")
        XCTAssertEqual(points.filter { $0.style == .hollow }.map(\.x), [x("2026-10-12T05:44:00+00:00")])
        XCTAssertEqual(home.runs.count, 1)
        XCTAssertEqual(away.runs.flatMap(\.points).map(\.x), points.map(\.x), "the other side of the same rows")
        XCTAssertEqual(away.runs.flatMap(\.points).map(\.probability), points.map { 1 - $0.probability })
        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x("2026-10-11T05:45:00+00:00"),
                                                            upper: x("2026-10-12T05:44:00+00:00")))
        XCTAssertEqual(input.guides, [])
        XCTAssertEqual(input.caption, "Before game")
    }

    // MARK: - Whose history (#10868 hockey F1)

    private func relabelled(_ json: String, eventId: Int) throws -> EventHistoryResponse {
        try decoder().decode(EventHistoryResponse.self, from: try edited(json, setting: ["event_id": eventId]))
    }

    /// The page as the host glue builds it, with no markets or box (they are not under test).
    private func hostBuild(_ event: EventDetail, history: EventHistoryResponse?, now: String,
                           ladderHome: Double? = nil, ladderAway: Double? = nil) throws -> HockeyJourneyPageInput10868 {
        HockeyJourneyEventPageHost10868.build(
            event: event, history: history, markets: nil, boxScore: nil,
            probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
            ladderHome: ladderHome, ladderAway: ladderAway,
            now: try XCTUnwrap(now.asDate), calendar: Self.pacific, locale: Locale(identifier: "en_US")).input
    }

    /// The before matrix's two forecast slots, home then away; nil off the before phase.
    private func forecast(_ input: HockeyJourneyPageInput10868) -> [HockeyJourneySlot10868]? {
        guard case .before(let matrix) = input.headline.matrix else { return nil }
        return [matrix.home.projectedGoals, matrix.away.projectedGoals]
    }

    private var noForecast: [HockeyJourneySlot10868] {
        [.absent(A.Words.noPregameForecast), .absent(A.Words.noPregameForecast)]
    }

    /// TEST MUTATION: the retained Rams detail with its served sportsbook projections removed,
    /// so the before-the-start pair in play can only be the ladders'.
    private func ramsWithoutSportsbookPair() throws -> EventDetail {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(Self.ramsDetail.utf8)) as? [String: Any])
        var odds = try XCTUnwrap(object["current_odds"] as? [String: Any])
        XCTAssertEqual(odds["projected_home_score"] as? Double, 29.0)
        XCTAssertEqual(odds["projected_away_score"] as? Double, 25.4)
        odds.removeValue(forKey: "projected_home_score")
        odds.removeValue(forKey: "projected_away_score")
        object["current_odds"] = odds
        return try decoder().decode(EventDetail.self, from: try JSONSerialization.data(withJSONObject: object))
    }

    /// N1. The real 15169793 body (Wild–Bruins) held on the page of 15338496 (Devils at Golden
    /// Knights) is drawn as no body at all, in every phase. The relabelled ids are TEST CONTROLS:
    /// the same bytes under this game's id draw, and this game's own bytes under another id do not.
    func testTheChartReaderDrawsAnotherGamesBodyAsNoBody() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let foreign = try response(Self.wildBruinsHistory)
        XCTAssertEqual(foreign.eventId, 15169793)
        XCTAssertEqual(event.id, 15338496)
        let host = readerHost("2026-10-30T20:13:55Z")
        for phase in [HockeyJourneyPagePhase10868.before, .live, .final] {
            XCTAssertEqual(H.history(foreign, event: event, phase: phase, host: host),
                           H.unavailable(event: event, phase: phase))
        }
        let unavailable = H.unavailable(event: event, phase: .before)
        XCTAssertNotEqual(H.history(try relabelled(Self.wildBruinsHistory, eventId: event.id),
                                    event: event, phase: .before, host: host), unavailable)
        XCTAssertEqual(H.history(try relabelled(Self.devilsKnightsHistory, eventId: 15169793),
                                 event: event, phase: .before, host: host), unavailable)
        XCTAssertNotEqual(H.history(try response(Self.devilsKnightsHistory), event: event, phase: .before, host: host),
                          unavailable)
    }

    /// N2. The host builds exactly the no-body page from another game's body: "History
    /// unavailable", no borrowed series id or note, no Full chart. The own chance, stories and
    /// copy are those of the page with this game's own body.
    func testTheHostBuildsTheNoBodyPageFromAnotherGamesBody() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let now = "2026-10-30T20:13:55Z"
        let page = try hostBuild(event, history: try response(Self.wildBruinsHistory), now: now)
        let missing = try hostBuild(event, history: nil, now: now)
        let own = try hostBuild(event, history: try response(Self.devilsKnightsHistory), now: now)
        XCTAssertEqual(page, missing)
        XCTAssertEqual(page.history, H.unavailable(event: event, phase: .before))
        XCTAssertEqual(page.history.plotAbsence, FieldHistoryPlotAbsence10868(title: "History unavailable", words: nil))
        XCTAssertNil(page.history.expand)
        XCTAssertEqual(page.history.notes, [])
        XCTAssertFalse(page.history.series.contains { $0.id.contains("15169793") })
        XCTAssertEqual(page.headline, own.headline)
        XCTAssertEqual(page.points, own.points)
        XCTAssertEqual(page.assists, own.assists)
        XCTAssertEqual(page.stories, own.stories)
        XCTAssertEqual(page.copy, own.copy)
        XCTAssertNotEqual(own.history, page.history)
    }

    /// N3. TEST CONTROL, NOT HOCKEY FORECAST EVIDENCE: `LiveProjectedFinalAdmission2920` refuses
    /// every hockey pair, so a history-derived ladder pair is reached only through this NFL event
    /// with its sportsbook projections removed (TEST MUTATION). Another game's ladder (3.7 / 2.4)
    /// supplies no forecast; under this game's id the same bytes print; this game's own body's
    /// verbatim `pm_spread_data.projected_final` (28.8 / 25.5, Kalshi) prints.
    func testABeforeTheStartForecastIsNeverReadFromAnotherGamesBody() throws {
        XCTAssertNil(LiveProjectedFinalAdmission2920.format(forSport: "icehockey_nhl"))
        XCTAssertNotNil(LiveProjectedFinalAdmission2920.format(forSport: "americanfootball_nfl"))
        let event = try ramsWithoutSportsbookPair()
        let now = "2026-10-12T05:45:12Z"
        let foreign = try response(Self.devilsKnightsHistory)
        XCTAssertEqual(foreign.pmSpreadData?.projectedFinal?.homeScore, 3.7)
        XCTAssertEqual(foreign.pmSpreadData?.projectedFinal?.awayScore, 2.4)
        let page = try hostBuild(event, history: foreign, now: now)
        XCTAssertEqual(page, try hostBuild(event, history: nil, now: now))
        XCTAssertEqual(forecast(page), noForecast)
        let relabelledPage = try hostBuild(event, history: try relabelled(Self.devilsKnightsHistory, eventId: event.id),
                                           now: now)
        XCTAssertEqual(forecast(relabelledPage), [A.forecastSlot(3.7), A.forecastSlot(2.4)])
        let own = try response(Self.ramsHistory)
        XCTAssertEqual(own.pmSpreadData?.projectedFinal?.homeScore, 28.8)
        XCTAssertEqual(own.pmSpreadData?.projectedFinal?.awayScore, 25.5)
        let ownPage = try hostBuild(event, history: own, now: now)
        XCTAssertEqual(forecast(ownPage), [A.forecastSlot(28.8), A.forecastSlot(25.5)])
        guard case .before(let matrix) = ownPage.headline.matrix else { return XCTFail("before matrix") }
        XCTAssertEqual(matrix.projectedGoals.provenance, "Prediction-market lines before the start")
    }

    /// The preserved legacy scalars never replace the identity-bound pair. With this game's own
    /// body held, the passed bare doubles (the other game's 3.7 / 2.4, TEST CONTROL) change
    /// nothing; with no body, another game's body, or an own body without a ladder pair, they
    /// supply nothing. Same NFL-keyed TEST MUTATION as N3.
    func testPassedBareLadderDoublesNeverReplaceTheOwnBodysPair() throws {
        let event = try ramsWithoutSportsbookPair()
        let now = "2026-10-12T05:45:12Z"
        let own = try response(Self.ramsHistory)
        let bound = try hostBuild(event, history: own, now: now)
        let withScalars = try hostBuild(event, history: own, now: now, ladderHome: 3.7, ladderAway: 2.4)
        XCTAssertEqual(withScalars, bound)
        XCTAssertEqual(forecast(withScalars), [A.forecastSlot(28.8), A.forecastSlot(25.5)])
        let none = try hostBuild(event, history: nil, now: now, ladderHome: 3.7, ladderAway: 2.4)
        XCTAssertEqual(none, try hostBuild(event, history: nil, now: now))
        XCTAssertEqual(forecast(none), noForecast)
        XCTAssertEqual(forecast(try hostBuild(event, history: try response(Self.devilsKnightsHistory), now: now,
                                              ladderHome: 3.7, ladderAway: 2.4)), noForecast)
        let unladdered = try decoder().decode(EventHistoryResponse.self,
                                              from: try edited(Self.ramsHistory, removing: ["pm_spread_data"])) // CONSTRUCTED
        XCTAssertEqual(unladdered.eventId, event.id)
        XCTAssertNil(unladdered.pmSpreadData?.projectedFinal)
        XCTAssertEqual(forecast(try hostBuild(event, history: unladdered, now: now, ladderHome: 3.7, ladderAway: 2.4)),
                       noForecast)
        // An NHL page with its own body: the scalars change nothing there either.
        let nhl = try detail(Self.devilsKnightsDetail)
        let nhlOwn = try response(Self.devilsKnightsHistory)
        XCTAssertEqual(try hostBuild(nhl, history: nhlOwn, now: "2026-10-30T20:13:55Z", ladderHome: 3.7, ladderAway: 2.4),
                       try hostBuild(nhl, history: nhlOwn, now: "2026-10-30T20:13:55Z"))
    }

    // MARK: - Retained bodies

    private static let wildBruinsDetail = ##"""
{"id":15169793,"external_id":"3a9af73961ea2f2322255a6fca4d421e","sport":"icehockey_nhl","sport_name":"NHL","home_team":"Minnesota Wild","away_team":"Boston Bruins","commence_time":"2026-10-04T00:00:00+00:00","start_is_tbd":false,"completed_at":"2026-10-04T02:48:56.423990+00:00","status":"completed","started_without_result":false,"home_score":4,"away_score":1,"score_source":"espn","score_observed_at":"2026-10-04T05:59:38.451734+00:00","home_team_data":{"team_id":575,"slug":"minnesota-wild","primary_color":"#124734","secondary_color":"#ae122a","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/min.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/min.png","record":"2-1-1","abbreviation":"MIN","standings":{"pct":".667","wins":2,"losses":1,"points":5,"streak":"L2","div_rank":4,"division":"Central Division","goals_for":11,"conference":"Western Conference","home_record":"1-0-0","road_record":"1-1-1","goals_against":8,"draws":1}},"away_team_data":{"team_id":574,"slug":"boston-bruins","primary_color":"#231f20","secondary_color":"#fdb71a","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/bos.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/bos.png","record":"3-2-0","abbreviation":"BOS","standings":{"pct":".600","wins":3,"losses":2,"points":6,"streak":"W1","div_rank":4,"division":"Atlantic Division","goals_for":15,"conference":"Eastern Conference","home_record":"2-1-0","road_record":"1-1-0","goals_against":12,"draws":0}},"metadata":{"gender":"men","level":"professional","league":"NHL","importance":"regular_season"},"espn":{"espn_id":"401891814","game_clock":"0:00","period":"Final","broadcast":"ESPN+, MINNHL, KSTC","probability_sources":{"stat_model":0.999,"betting_book_count":2.0}},"win_probability_sources":{"stat_model":{"value":0.999,"display_name":"Bain Luck Model","type":"model","color":"#8b5cf6","updated_at":"2026-10-04T02:47:58.048106+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":2.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":39,"raw_score":37,"status":"quiet","label":"Quiet","emoji":"😴","metadata":{"raw_ei":0.3407,"lead_changes":2,"comeback_factor":0.431,"snapshot_count":337}},"pulse":{"score":39,"raw_score":37,"status":"quiet","label":"Quiet","emoji":"😴","metadata":{"raw_ei":0.3407,"lead_changes":2,"comeback_factor":0.431,"snapshot_count":337}},"event_tags":["audience:national_interest","class:pro_major","competitive_structure:head_to_head","ei:quiet","gender:men","importance:regular_season","league:nhl","level:professional","sport:hockey","stakes:playoff_race","status:completed","tier:1","timing:national_tv","timing:primetime","timing:weekend"],"standings_context":{"home":"2-1-1, #4 Central, 5 pts","away":"3-2-0, #4 Atlantic, 6 pts"},"current_odds":{"captured_at":"2026-10-04T02:46:59.868080+00:00","home_probability":0.999,"away_probability":0.001,"away_rendered_percent":0,"home_rendered_percent":100,"spread":-2.1,"over_under":5.1,"projected_home_score":3.6,"projected_away_score":1.5,"bookmaker_count":6},"bookmaker_odds":[{"bookmaker":"ballybet","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:38:52.650155+00:00","spread":-1.5,"over_under":4.5,"projected_home_score":3.0,"projected_away_score":1.5},{"bookmaker":"betanysports","home_moneyline":-220,"away_moneyline":180,"home_probability":0.6581,"away_probability":0.3419,"captured_at":"2026-10-03T23:21:58.853931+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betmgm","home_moneyline":-10000,"away_moneyline":3300,"home_probability":0.9712,"away_probability":0.0288,"captured_at":"2026-10-04T02:45:52.104311+00:00","spread":-3.5,"over_under":5.5,"projected_home_score":4.5,"projected_away_score":1.0},{"bookmaker":"betonlineag","home_moneyline":-207,"away_moneyline":181,"home_probability":0.6545,"away_probability":0.3455,"captured_at":"2026-10-04T00:05:53.974638+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betparx","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:39:28.975248+00:00","spread":-1.5,"over_under":4.5,"projected_home_score":3.0,"projected_away_score":1.5},{"bookmaker":"betrivers","home_moneyline":-215,"away_moneyline":175,"home_probability":0.6524,"away_probability":0.3476,"captured_at":"2026-10-03T23:38:13.229743+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"betus","home_moneyline":-205,"away_moneyline":175,"home_probability":0.6489,"away_probability":0.3511,"captured_at":"2026-10-04T00:05:53.983572+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"bovada","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:36:52.961250+00:00","spread":-2.5,"over_under":5.0,"projected_home_score":3.8,"projected_away_score":1.2},{"bookmaker":"courtside","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:46:59.868080+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"draftkings","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:37:56.212040+00:00","spread":-2.5,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0},{"bookmaker":"espnbet","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:39:28.955270+00:00","spread":-2.5,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0},{"bookmaker":"fanatics","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:41:01.577185+00:00","spread":-2.5,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0},{"bookmaker":"fanduel","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:39:28.971310+00:00","spread":-2.5,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0},{"bookmaker":"fliff","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:36:52.995271+00:00","spread":-2.5,"over_under":5.5,"projected_home_score":4.0,"projected_away_score":1.5},{"bookmaker":"hardrockbet","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:39:28.968653+00:00","spread":-2.5,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0},{"bookmaker":"lowvig","home_moneyline":-207,"away_moneyline":181,"home_probability":0.6545,"away_probability":0.3455,"captured_at":"2026-10-04T00:05:53.977569+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"mybookieag","home_moneyline":null,"away_moneyline":null,"home_probability":null,"away_probability":null,"captured_at":"2026-10-04T02:42:16.506991+00:00","spread":-2.5,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"rebet","home_moneyline":-188,"away_moneyline":152,"home_probability":0.6219,"away_probability":0.3781,"captured_at":"2026-10-03T00:16:36.981072+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"williamhill_us","home_moneyline":-10000,"away_moneyline":1400,"home_probability":0.9369,"away_probability":0.0631,"captured_at":"2026-10-04T02:41:01.560531+00:00","spread":null,"over_under":4.5,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.6549,"away_probability":0.3451,"spread":-1.5,"over_under":6.5,"favorite":"home"},"prematch_odds":{"home_probability":0.66,"away_probability":0.34,"home_rendered_percent":66,"away_rendered_percent":34,"source":"kalshi"},"hero_probability_observed_at":null,"blend_fold_revision":{"15169793":6051},"hero_probability":1.0,"hero_probability_away":0.0,"hero_probability_source":"settled","hero_settled_result":"home","box_score_data":{"players":{"JJ Peterka":{"hits":0.0,"goals":0.0,"shots":2.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Matt Boldy":{"hits":2.0,"goals":0.0,"shots":4.0,"assists":0.0,"giveaways":1.0,"takeaways":1.0,"plus minus":1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Bobby Brink":{"hits":1.0,"goals":0.0,"shots":1.0,"assists":1.0,"giveaways":1.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Daemon Hunt":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":2.0},"Olli Maatta":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":3.0,"takeaways":1.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Pavel Zacha":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":7.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Sean Kuraly":{"hits":0.0,"goals":0.0,"shots":3.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":5.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Will Borgen":{"hits":3.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":3.0,"shootout goals":0.0,"penalty minutes":0.0},"Danila Yurov":{"hits":1.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":1.0,"takeaways":1.0,"plus minus":0.0,"faceoffs won":6.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"James Hagens":{"hits":1.0,"goals":0.0,"shots":3.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Jonas Brodin":{"hits":0.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":2.0,"takeaways":1.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Mason Lohrei":{"hits":0.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":1.0,"takeaways":1.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Nick Foligno":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":2.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Quinn Hughes":{"hits":0.0,"goals":1.0,"shots":4.0,"assists":1.0,"giveaways":1.0,"takeaways":1.0,"plus minus":1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Ryan Hartman":{"hits":0.0,"goals":0.0,"shots":0.0,"assists":1.0,"giveaways":1.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":5.0,"blocked shots":2.0,"shootout goals":0.0,"penalty minutes":2.0},"Yakov Trenin":{"hits":4.0,"goals":0.0,"shots":4.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Blake Coleman":{"hits":1.0,"goals":0.0,"shots":2.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Fraser Minten":{"hits":0.0,"goals":0.0,"shots":3.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":3.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Mark Kastelic":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":1.0,"giveaways":2.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":2.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Morgan Geekie":{"hits":3.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Zach Bogosian":{"hits":0.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Connor Clifton":{"hits":0.0,"goals":0.0,"shots":0.0,"assists":1.0,"giveaways":3.0,"takeaways":1.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":2.0},"David Pastrnak":{"hits":2.0,"goals":0.0,"shots":5.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Elias Lindholm":{"hits":0.0,"goals":0.0,"shots":2.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":14.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Jared Spurgeon":{"hits":0.0,"goals":1.0,"shots":1.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":2.0,"faceoffs won":0.0,"blocked shots":2.0,"shootout goals":0.0,"penalty minutes":2.0},"Marcus Foligno":{"hits":1.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":2.0,"takeaways":1.0,"plus minus":1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Maxim Shabanov":{"hits":1.0,"goals":0.0,"shots":0.0,"assists":1.0,"giveaways":1.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Nikita Zadorov":{"hits":3.0,"goals":0.0,"shots":2.0,"assists":0.0,"giveaways":2.0,"takeaways":1.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":2.0,"shootout goals":0.0,"penalty minutes":2.0},"Tanner Jeannot":{"hits":1.0,"goals":1.0,"shots":1.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Hampus Lindholm":{"hits":2.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":0.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},"Kirill Kaprizov":{"hits":0.0,"goals":2.0,"shots":3.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":1.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Jesper Wallstedt":{"saves":26.0,"goals against":1.0,"shots against":27.0,"penalty minutes":0.0,"save percentage":0.963},"Joel Eriksson Ek":{"hits":1.0,"goals":0.0,"shots":2.0,"assists":1.0,"giveaways":0.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":7.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Jonathan Aspirot":{"hits":1.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":2.0,"shootout goals":0.0,"penalty minutes":0.0},"Michael DiPietro":{"saves":26.0,"goals against":3.0,"shots against":29.0,"penalty minutes":0.0,"save percentage":0.897},"Michael McCarron":{"hits":2.0,"goals":0.0,"shots":4.0,"assists":1.0,"giveaways":2.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":7.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},"Casey Mittelstadt":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":1.0,"takeaways":1.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":2.0},"Marat Khusnutdinov":{"hits":0.0,"goals":0.0,"shots":1.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0}},"home_period_scores":[0,2,2],"away_period_scores":[1,0,0]}}
"""##

    private static let wildBruinsHistory = ##"""
{"event_id":15169793,
"home_team":"Minnesota Wild",
"away_team":"Boston Bruins",
"commence_time":"2026-10-04T00:00:00+00:00",
"completed_at":"2026-10-04T02:48:56.423990+00:00",
"status":"completed",
"time_domain":{"start":"2026-10-04T00:00:00+00:00","end":"2026-10-04T03:18:56.423990+00:00","is_live":false,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-10-02T23:37:00+00:00","home_probability":0.6223,"away_probability":0.3777,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":7,"probability_range":{"min":0.6164,"max":0.6344}},
{"timestamp":"2026-10-02T23:38:00+00:00","home_probability":0.6223,"away_probability":0.3777,"over_under":6.4,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":7,"probability_range":{"min":0.6164,"max":0.6344}},
{"timestamp":"2026-10-03T00:05:00+00:00","home_probability":0.6223,"away_probability":0.3777,"over_under":6.4,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":7,"probability_range":{"min":0.6164,"max":0.6344}},
{"timestamp":"2026-10-03T00:16:00+00:00","home_probability":0.6219,"away_probability":0.3781,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2,"bookmaker_count":1,"probability_range":{"min":0.6219,"max":0.6219}},
{"timestamp":"2026-10-03T23:26:00+00:00","home_probability":0.6565,"away_probability":0.3435,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6565,"max":0.6565}},
{"timestamp":"2026-10-03T23:37:00+00:00","home_probability":0.6532,"away_probability":0.3468,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":11,"probability_range":{"min":0.6448,"max":0.6581}},
{"timestamp":"2026-10-03T23:38:00+00:00","home_probability":0.6532,"away_probability":0.3468,"over_under":6.2,"projected_home_score":3.9,"projected_away_score":2.3,"bookmaker_count":11,"probability_range":{"min":0.6448,"max":0.6581}},
{"timestamp":"2026-10-03T23:45:00+00:00","home_probability":0.6565,"away_probability":0.3435,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6565,"max":0.6565}},
{"timestamp":"2026-10-03T23:46:00+00:00","home_probability":0.6565,"away_probability":0.3435,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6565,"max":0.6565}},
{"timestamp":"2026-10-04T00:00:00+00:00","home_probability":0.6557,"away_probability":0.3443,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":3,"probability_range":{"min":0.6456,"max":0.6675}},
{"timestamp":"2026-10-04T00:05:00+00:00","home_probability":0.6532,"away_probability":0.3468,"over_under":6.2,"projected_home_score":3.9,"projected_away_score":2.3,"bookmaker_count":10,"probability_range":{"min":0.6448,"max":0.6581}},
{"timestamp":"2026-10-04T00:08:00+00:00","home_probability":0.6379,"away_probability":0.3621,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6379,"max":0.6379}},
{"timestamp":"2026-10-04T00:10:00+00:00","home_probability":0.6597,"away_probability":0.3403,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6597,"max":0.6597}},
{"timestamp":"2026-10-04T00:11:00+00:00","home_probability":0.6597,"away_probability":0.3403,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":1,"probability_range":{"min":0.6597,"max":0.6597}},
{"timestamp":"2026-10-04T00:14:00+00:00","home_probability":0.6541,"away_probability":0.3459,"over_under":6.2,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":2,"probability_range":{"min":0.6534,"max":0.6548}},
{"timestamp":"2026-10-04T00:15:00+00:00","home_probability":0.6401,"away_probability":0.3599,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":9,"probability_range":{"min":0.6164,"max":0.6531}},
{"timestamp":"2026-10-04T00:16:00+00:00","home_probability":0.6495,"away_probability":0.3505,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5,"bookmaker_count":6,"probability_range":{"min":0.6413,"max":0.6556}},
{"timestamp":"2026-10-04T00:17:00+00:00","home_probability":0.6397,"away_probability":0.3603,"over_under":5.7,"projected_home_score":3.6,"projected_away_score":2.1,"bookmaker_count":12,"probability_range":{"min":0.6161,"max":0.6556}},
{"timestamp":"2026-10-04T00:18:00+00:00","home_probability":0.5806,"away_probability":0.4194,"over_under":6.0,"projected_home_score":3.3,"projected_away_score":2.8,"bookmaker_count":4,"probability_range":{"min":0.4899,"max":0.6626}},
{"timestamp":"2026-10-04T00:19:00+00:00","home_probability":0.4993,"away_probability":0.5007,"over_under":7.0,"projected_home_score":3.4,"projected_away_score":3.6,"bookmaker_count":10,"probability_range":{"min":0.4797,"max":0.5101}},
{"timestamp":"2026-10-04T00:20:00+00:00","home_probability":0.5266,"away_probability":0.4734,"over_under":6.6,"projected_home_score":3.1,"projected_away_score":3.4,"bookmaker_count":6,"probability_range":{"min":0.4951,"max":0.6463}},
{"timestamp":"2026-10-04T00:22:00+00:00","home_probability":0.497,"away_probability":0.503,"over_under":6.5,"projected_home_score":2.9,"projected_away_score":3.7,"bookmaker_count":10,"probability_range":{"min":0.4899,"max":0.5}},
{"timestamp":"2026-10-04T00:24:00+00:00","home_probability":0.4931,"away_probability":0.5069,"over_under":6.5,"projected_home_score":2.5,"projected_away_score":4.0,"bookmaker_count":8,"probability_range":{"min":0.4896,"max":0.5}},
{"timestamp":"2026-10-04T00:25:00+00:00","home_probability":0.4999,"away_probability":0.5001,"over_under":6.5,"projected_home_score":3.2,"projected_away_score":3.2,"bookmaker_count":5,"probability_range":{"min":0.4899,"max":0.5147}},
{"timestamp":"2026-10-04T02:32:00+00:00","home_probability":0.9378,"away_probability":0.0622,"over_under":5.5,"projected_home_score":4.0,"projected_away_score":1.5,"bookmaker_count":4,"probability_range":{"min":0.9321,"max":0.9469}},
{"timestamp":"2026-10-04T02:33:00+00:00","home_probability":0.9498,"away_probability":0.0502,"over_under":5.5,"projected_home_score":3.8,"projected_away_score":1.8,"bookmaker_count":3,"probability_range":{"min":0.9434,"max":0.9578}},
{"timestamp":"2026-10-04T02:34:00+00:00","home_probability":0.9481,"away_probability":0.0519,"over_under":5.5,"projected_home_score":4.0,"projected_away_score":1.5,"bookmaker_count":5,"probability_range":{"min":0.9205,"max":0.9627}},
{"timestamp":"2026-10-04T02:35:00+00:00","home_probability":0.951,"away_probability":0.049,"over_under":5.5,"projected_home_score":3.9,"projected_away_score":1.6,"bookmaker_count":9,"probability_range":{"min":0.9266,"max":0.9685}},
{"timestamp":"2026-10-04T02:36:00+00:00","home_probability":0.9687,"away_probability":0.0314,"over_under":5.4,"projected_home_score":3.9,"projected_away_score":1.5,"bookmaker_count":4,"probability_range":{"min":0.9626,"max":0.9729}},
{"timestamp":"2026-10-04T02:37:00+00:00","home_probability":0.9706,"away_probability":0.0294,"over_under":5.2,"projected_home_score":3.8,"projected_away_score":1.4,"bookmaker_count":5,"probability_range":{"min":0.9626,"max":0.9807}},
{"timestamp":"2026-10-04T02:38:00+00:00","home_probability":0.9747,"away_probability":0.0253,"over_under":4.5,"projected_home_score":3.3,"projected_away_score":1.2,"bookmaker_count":4,"probability_range":{"min":0.9687,"max":0.9861}},
{"timestamp":"2026-10-04T02:39:00+00:00","home_probability":null,"away_probability":null,"over_under":4.5,"projected_home_score":3.4,"projected_away_score":1.1,"bookmaker_count":0,"probability_range":{"min":null,"max":null}},
{"timestamp":"2026-10-04T02:41:00+00:00","home_probability":0.9369,"away_probability":0.0631,"over_under":4.5,"projected_home_score":3.5,"projected_away_score":1.0,"bookmaker_count":1,"probability_range":{"min":0.9369,"max":0.9369}},
{"timestamp":"2026-10-04T02:42:00+00:00","home_probability":null,"away_probability":null,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":0,"probability_range":{"min":null,"max":null}},
{"timestamp":"2026-10-04T02:43:00+00:00","home_probability":0.9712,"away_probability":0.0288,"over_under":5.0,"projected_home_score":3.8,"projected_away_score":1.2,"bookmaker_count":1,"probability_range":{"min":0.9712,"max":0.9712}},
{"timestamp":"2026-10-04T02:45:00+00:00","home_probability":0.9712,"away_probability":0.0288,"over_under":5.5,"projected_home_score":4.5,"projected_away_score":1.0,"bookmaker_count":1,"probability_range":{"min":0.9712,"max":0.9712}},
{"timestamp":"2026-10-04T02:46:00+00:00","home_probability":null,"away_probability":null,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0,"bookmaker_count":0,"probability_range":{"min":null,"max":null}},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0,"away_probability":0.0,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":0,"probability_range":{"min":1.0,"max":1.0}}
],
"bookmaker_history":{},
"score_history":[{"timestamp":"2026-10-04T00:14:57.965570+00:00","home_score":0,"away_score":0},{"timestamp":"2026-10-04T00:19:13.520233+00:00","home_score":0,"away_score":1},{"timestamp":"2026-10-04T00:24:48.324147+00:00","home_score":0,"away_score":0},{"timestamp":"2026-10-04T00:24:59.583272+00:00","home_score":0,"away_score":1},{"timestamp":"2026-10-04T01:23:47.961713+00:00","home_score":1,"away_score":1},{"timestamp":"2026-10-04T01:29:13.715118+00:00","home_score":0,"away_score":1},{"timestamp":"2026-10-04T01:29:58.516427+00:00","home_score":1,"away_score":1},{"timestamp":"2026-10-04T01:40:13.610746+00:00","home_score":2,"away_score":1},{"timestamp":"2026-10-04T02:15:56.622760+00:00","home_score":3,"away_score":1},{"timestamp":"2026-10-04T02:45:57.165485+00:00","home_score":4,"away_score":1},{"timestamp":"2026-10-04T02:46:13.649604+00:00","home_score":3,"away_score":1},{"timestamp":"2026-10-04T02:46:59.608555+00:00","home_score":4,"away_score":1}],
"espn_history":[
{"timestamp":"2026-10-04T00:14:57.965570+00:00","home_probability":null,"away_probability":null,"home_score":0,"away_score":0,"game_clock":"20:00","period":"20:00 - 1st Period"},
{"timestamp":"2026-10-04T01:10:59.081904+00:00","home_probability":null,"away_probability":null,"home_score":0,"away_score":1,"game_clock":"20:00","period":"20:00 - 2nd Period"},
{"timestamp":"2026-10-04T02:08:56.957013+00:00","home_probability":null,"away_probability":null,"home_score":2,"away_score":1,"game_clock":"20:00","period":"20:00 - 3rd Period"},
{"timestamp":"2026-10-04T02:47:57.876818+00:00","home_probability":null,"away_probability":null,"home_score":4,"away_score":1,"game_clock":"0:24","period":"0:24 - 3rd Period"},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0,"away_probability":0.0,"home_score":4,"away_score":1,"game_clock":"Final","period":"Final"}
],
"win_prob_history":{
"polymarket":[
{"timestamp":"2026-09-06T15:50:00+00:00","home_probability":0.5,"away_probability":0.5,"draw_probability":null,"game_state":null,"evidence":{"kind":"candle"}},
{"timestamp":"2026-10-04T02:49:04.418724+00:00","home_probability":0.9995,"away_probability":0.0005,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-04T03:14:00.149449+00:00","home_probability":0.999,"away_probability":0.001,"draw_probability":null,"game_state":null,"evidence":{"kind":"terminal_row"}},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0,"away_probability":0.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}
],
"kalshi":[
{"timestamp":"2026-09-27T01:07:00+00:00","home_probability":0.485,"away_probability":0.515,"draw_probability":null,"game_state":null,"evidence":{"kind":"candle"}},
{"timestamp":"2026-10-04T02:47:59.037419+00:00","home_probability":0.995,"away_probability":0.005,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-04T02:48:44.442930+00:00","home_probability":0.995,"away_probability":0.005,"draw_probability":null,"game_state":null,"evidence":{"kind":"terminal_row"}},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0,"away_probability":0.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}
],
"stat_model":[
{"timestamp":"2026-10-04T00:14:57.965570+00:00","home_probability":0.7257,"away_probability":0.2743,"draw_probability":null,"game_state":{"clock":"20:00","period":"20:00 - 1st Period","away_score":0,"home_score":0,"time_source":"espn"}},
{"timestamp":"2026-10-04T00:15:57.708100+00:00","home_probability":0.7252,"away_probability":0.2748,"draw_probability":null,"game_state":{"clock":"19:41","period":"19:41 - 1st Period","away_score":0,"home_score":0,"time_source":"espn"}},
{"timestamp":"2026-10-04T02:45:57.165485+00:00","home_probability":0.999,"away_probability":0.001,"draw_probability":null,"game_state":{"clock":"1:01","period":"1:01 - 3rd Period","away_score":1,"home_score":4,"time_source":"espn"}},
{"timestamp":"2026-10-04T02:47:57.876818+00:00","home_probability":0.999,"away_probability":0.001,"draw_probability":null,"game_state":{"clock":"0:24","period":"0:24 - 3rd Period","away_score":1,"home_score":4,"time_source":"espn"},"evidence":{"kind":"terminal_row"}},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0,"away_probability":0.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}
]
},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":1532},"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":870},"stat_model":{"display_name":"Bain Luck Model","type":"model","color":"#8b5cf6","dash_pattern":"4 4","description":"An open win probability model using sport-specific methodology. Clock sports (NFL, NBA, NHL) use a normal distribution model inspired by nflfastR. Baseball uses a Poisson run-scoring model based on Tom Tango's methodology.","methodology":"Clock sports: Based on Hal Stern's research. Final margin modeled as N(score_diff + spread × remaining_fraction, base_std × √remaining_fraction). Baseball: Based on Tom Tango's 'The Book'. Remaining runs modeled as Poisson(runs_per_half_inning × half_innings_remaining). Normal approximation gives P(home wins) accounting for asymmetric half-innings, walk-off rule, and home field advantage (~54% historical home win rate).","attribution_url":"https://www.pro-football-reference.com/about/win_prob.htm","attribution_name":"nflfastR / PFR methodology","snapshot_count":104}},
"scoring_plays":[],
"moments":[],
"period_markers":[
{"timestamp":"2026-10-04T00:14:57.965570+00:00","period":"20:00 - 1st Period","source":"win_prob"},
{"timestamp":"2026-10-04T00:53:57.528612+00:00","period":"End of 1st Period","source":"win_prob"},
{"timestamp":"2026-10-04T01:10:59.081904+00:00","period":"20:00 - 2nd Period","source":"win_prob"},
{"timestamp":"2026-10-04T01:51:57.556005+00:00","period":"End of 2nd Period","source":"win_prob"},
{"timestamp":"2026-10-04T02:08:56.957013+00:00","period":"20:00 - 3rd Period","source":"win_prob"}
],
"aggregate_line":[
{"timestamp":"2026-10-02T23:52:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-02T23:55:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T00:01:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T00:02:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T00:04:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T00:05:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T00:09:00+00:00","home_probability":0.645},
{"timestamp":"2026-10-03T12:04:00+00:00","home_probability":0.6464},
{"timestamp":"2026-10-03T12:05:00+00:00","home_probability":0.6458},
{"timestamp":"2026-10-03T12:10:00+00:00","home_probability":0.6458},
{"timestamp":"2026-10-03T12:11:00+00:00","home_probability":0.6458},
{"timestamp":"2026-10-03T23:44:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:45:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:46:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:47:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:48:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:49:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:50:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:51:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:54:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:56:00+00:00","home_probability":0.66},
{"timestamp":"2026-10-03T23:57:00+00:00","home_probability":0.66},
{"timestamp":"2026-10-03T23:58:00+00:00","home_probability":0.665},
{"timestamp":"2026-10-03T23:59:00+00:00","home_probability":0.66},
{"timestamp":"2026-10-04T00:00:00+00:00","home_probability":0.65687},
{"timestamp":"2026-10-04T00:01:00+00:00","home_probability":0.65687},
{"timestamp":"2026-10-04T00:02:00+00:00","home_probability":0.65687},
{"timestamp":"2026-10-04T00:03:00+00:00","home_probability":0.65687},
{"timestamp":"2026-10-04T00:05:00+00:00","home_probability":0.655995},
{"timestamp":"2026-10-04T00:06:00+00:00","home_probability":0.655995},
{"timestamp":"2026-10-04T00:08:00+00:00","home_probability":0.65389},
{"timestamp":"2026-10-04T00:09:00+00:00","home_probability":0.658765},
{"timestamp":"2026-10-04T00:10:00+00:00","home_probability":0.666395},
{"timestamp":"2026-10-04T00:11:00+00:00","home_probability":0.666395},
{"timestamp":"2026-10-04T00:12:00+00:00","home_probability":0.66802},
{"timestamp":"2026-10-04T00:13:00+00:00","home_probability":0.66802},
{"timestamp":"2026-10-04T00:14:00+00:00","home_probability":0.67736},
{"timestamp":"2026-10-04T00:15:00+00:00","home_probability":0.672335},
{"timestamp":"2026-10-04T00:16:00+00:00","home_probability":0.67715},
{"timestamp":"2026-10-04T00:17:00+00:00","home_probability":0.666645},
{"timestamp":"2026-10-04T00:18:00+00:00","home_probability":0.58786},
{"timestamp":"2026-10-04T00:19:00+00:00","home_probability":0.551855},
{"timestamp":"2026-10-04T00:53:00+00:00","home_probability":0.484655},
{"timestamp":"2026-10-04T01:20:00+00:00","home_probability":0.451085},
{"timestamp":"2026-10-04T01:21:00+00:00","home_probability":0.467405},
{"timestamp":"2026-10-04T01:22:00+00:00","home_probability":0.541215},
{"timestamp":"2026-10-04T01:23:00+00:00","home_probability":0.63359},
{"timestamp":"2026-10-04T01:24:00+00:00","home_probability":0.64297},
{"timestamp":"2026-10-04T01:42:00+00:00","home_probability":0.814255},
{"timestamp":"2026-10-04T01:43:00+00:00","home_probability":0.81795},
{"timestamp":"2026-10-04T01:44:00+00:00","home_probability":0.818645},
{"timestamp":"2026-10-04T01:45:00+00:00","home_probability":0.81574},
{"timestamp":"2026-10-04T01:46:00+00:00","home_probability":0.81609},
{"timestamp":"2026-10-04T02:12:00+00:00","home_probability":0.82449},
{"timestamp":"2026-10-04T02:13:00+00:00","home_probability":0.824265},
{"timestamp":"2026-10-04T02:14:00+00:00","home_probability":0.86258},
{"timestamp":"2026-10-04T02:15:00+00:00","home_probability":0.941665},
{"timestamp":"2026-10-04T02:16:00+00:00","home_probability":0.95104},
{"timestamp":"2026-10-04T02:43:00+00:00","home_probability":0.97977},
{"timestamp":"2026-10-04T02:44:00+00:00","home_probability":0.98177},
{"timestamp":"2026-10-04T02:45:00+00:00","home_probability":0.98757},
{"timestamp":"2026-10-04T02:46:00+00:00","home_probability":0.98757},
{"timestamp":"2026-10-04T02:47:00+00:00","home_probability":0.98857},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":0.98847},
{"timestamp":"2026-10-04T02:49:00+00:00","home_probability":0.98857},
{"timestamp":"2026-10-04T03:14:00+00:00","home_probability":0.988654},
{"timestamp":"2026-10-04T02:48:00+00:00","home_probability":1.0}
],
"blend_edge_pinned":false,
"blend_edge_observed_at":null,
"blend_edge_fold_revision":null,
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"sportsbook":{"spread":-1.5,"home_margin":1.5,"confidence":1.0,"contracts":[]}},"implied_totals":{"sportsbook":{"total":5.5,"confidence":1.0,"contracts":[]}},"projected_final":null},
"points":494,
"bookmaker_count":19,
"snapshot_count":2423,
"espn_snapshot_count":121,
"on_demand_backfill":null}
"""##

    private static let devilsKnightsDetail = ##"""
{"id":15338496,"external_id":"5c712e15e1cd4b9283b4bf410fb334f4","sport":"icehockey_nhl","sport_name":"NHL","home_team":"Vegas Golden Knights","away_team":"New Jersey Devils","commence_time":"2026-10-30T22:00:00+00:00","start_is_tbd":false,"start_is_from_schedule":true,"completed_at":null,"status":"scheduled","started_without_result":false,"home_score":null,"away_score":null,"home_team_data":{"team_id":63,"slug":"vegas-golden-knights","primary_color":"#344043","secondary_color":"#b4975a","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/vgk.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/vgk.png","record":"9-4-1","abbreviation":"VGK","standings":{"pct":".692","wins":9,"losses":4,"points":19,"streak":"W1","div_rank":2,"division":"Pacific Division","goals_for":51,"conference":"Western Conference","home_record":"6-2-0","road_record":"3-2-1","goals_against":39,"draws":1}},"away_team_data":{"team_id":53,"slug":"new-jersey-devils","primary_color":"#e30b2b","secondary_color":"#000000","logo_small":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nj.png","logo_large":"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nj.png","record":"8-5-0","abbreviation":"NJ","standings":{"pct":".615","wins":8,"losses":5,"points":16,"streak":"L1","div_rank":2,"division":"Metropolitan Division","goals_for":43,"conference":"Eastern Conference","home_record":"6-2-0","road_record":"2-3-0","goals_against":38,"draws":0}},"metadata":{"gender":"men","level":"professional","league":"NHL","importance":"regular_season"},"espn":{"espn_id":"401892611","broadcast":"NHL Net, MSGSN, Scripps Sports","probability_sources":{"kalshi":0.505,"betting":0.5052,"polymarket":0.505,"betting_book_count":19.0}},"win_probability_sources":{"kalshi":{"value":0.505,"display_name":"Kalshi","type":"market","color":"#22c55e","updated_at":"2026-10-30T20:12:18.516253+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031"},"betting":{"value":0.5052,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-30T20:11:38.149122+00:00","evidence_status":"not_applicable"},"polymarket":{"value":0.505,"display_name":"Polymarket","type":"market","color":"#3b82f6","updated_at":"2026-10-30T20:13:34.913575+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031","price_evidence":"unproven"},"betting_book_count":{"value":19.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"event_tags":["audience:national_interest","class:pro_major","competitive_structure:head_to_head","gender:men","importance:regular_season","league:nhl","level:professional","sport:hockey","stakes:playoff_race","status:scheduled","tier:1"],"standings_context":{"home":"9-4-1, #2 Pacific, 19 pts","away":"8-5-0, #2 Metropolitan, 16 pts"},"current_odds":{"captured_at":"2026-10-30T20:11:38.123766+00:00","home_probability":0.505,"away_probability":0.495,"away_rendered_percent":49,"home_rendered_percent":51,"spread":-0.8,"over_under":5.9,"projected_home_score":3.5,"projected_away_score":2.5,"bookmaker_count":19},"bookmaker_odds":[{"bookmaker":"ballybet","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:00:18.560393+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betanysports","home_moneyline":-115,"away_moneyline":-105,"home_probability":0.5108,"away_probability":0.4892,"captured_at":"2026-10-30T03:36:59.763124+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betmgm","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.046354+00:00","spread":1.5,"over_under":6.0,"projected_home_score":2.2,"projected_away_score":3.8},{"bookmaker":"betonlineag","home_moneyline":-111,"away_moneyline":-103,"home_probability":0.509,"away_probability":0.491,"captured_at":"2026-10-30T20:11:37.968853+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"betparx","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:00:18.492035+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betrivers","home_moneyline":-115,"away_moneyline":-104,"home_probability":0.512,"away_probability":0.488,"captured_at":"2026-10-30T20:11:38.094426+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"betus","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.062081+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"bovada","home_moneyline":-117,"away_moneyline":-103,"home_probability":0.5152,"away_probability":0.4848,"captured_at":"2026-10-30T20:11:38.123766+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"courtside","home_moneyline":-113,"away_moneyline":-103,"home_probability":0.5111,"away_probability":0.4889,"captured_at":"2026-10-30T20:00:18.410992+00:00","spread":1.5,"over_under":6.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-115,"away_moneyline":-105,"home_probability":0.5108,"away_probability":0.4892,"captured_at":"2026-10-30T20:11:37.932302+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"espnbet","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:00:18.476701+00:00","spread":1.5,"over_under":5.5,"projected_home_score":2.0,"projected_away_score":3.5},{"bookmaker":"fanatics","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:37.999661+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"fanduel","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:11:38.069388+00:00","spread":-1.5,"over_under":6.5,"projected_home_score":4.0,"projected_away_score":2.5},{"bookmaker":"fliff","home_moneyline":-115,"away_moneyline":-110,"home_probability":0.5052,"away_probability":0.4948,"captured_at":"2026-10-30T20:00:18.608502+00:00","spread":-1.5,"over_under":5.5,"projected_home_score":3.5,"projected_away_score":2.0},{"bookmaker":"hardrockbet","home_moneyline":-110,"away_moneyline":-110,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-30T20:00:18.569776+00:00","spread":1.5,"over_under":5.5,"projected_home_score":2.0,"projected_away_score":3.5},{"bookmaker":"lowvig","home_moneyline":-111,"away_moneyline":-103,"home_probability":0.509,"away_probability":0.491,"captured_at":"2026-10-30T20:11:37.938462+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"mybookieag","home_moneyline":-112,"away_moneyline":-109,"home_probability":0.5032,"away_probability":0.4968,"captured_at":"2026-10-30T20:11:38.114699+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"rebet","home_moneyline":-112,"away_moneyline":-109,"home_probability":0.5032,"away_probability":0.4968,"captured_at":"2026-10-30T20:00:18.375868+00:00","spread":-1.5,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2},{"bookmaker":"williamhill_us","home_moneyline":-111,"away_moneyline":-110,"home_probability":0.5011,"away_probability":0.4989,"captured_at":"2026-10-30T20:11:38.036259+00:00","spread":null,"over_under":6.0,"projected_home_score":null,"projected_away_score":null}],"hero_probability_observed_at":"2026-10-30T20:13:34.913575+00:00","blend_fold_revision":{"15338496":2376},"hero_probability":0.505,"hero_probability_away":0.495,"hero_probability_source":"blend","hero_sportsbook_count":19,"state_read_not_before":"2026-10-30T20:13:55.425936+00:00","state_read_not_after":"2026-10-30T20:13:55.430779+00:00","state_read_fresh":true}
"""##

    private static let devilsKnightsHistory = ##"""
{"event_id":15338496,
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"commence_time":"2026-10-30T22:00:00+00:00",
"completed_at":null,
"status":"scheduled",
"time_domain":{"start":"2026-10-29T20:13:00+00:00","end":"2026-10-30T20:13:59.771239+00:00","is_live":false,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-10-29T21:36:00+00:00","home_probability":0.508,"away_probability":0.492,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":9,"probability_range":{"min":0.5,"max":0.5164}},
{"timestamp":"2026-10-29T21:37:00+00:00","home_probability":0.5083,"away_probability":0.4917,"over_under":6.3,"projected_home_score":3.9,"projected_away_score":2.4,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5164}},
{"timestamp":"2026-10-29T22:04:00+00:00","home_probability":0.5118,"away_probability":0.4882,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2,"bookmaker_count":1,"probability_range":{"min":0.5118,"max":0.5118}},
{"timestamp":"2026-10-29T22:10:00+00:00","home_probability":0.518,"away_probability":0.482,"over_under":6.2,"projected_home_score":3.9,"projected_away_score":2.3,"bookmaker_count":3,"probability_range":{"min":0.5162,"max":0.5217}},
{"timestamp":"2026-10-30T19:38:00+00:00","home_probability":0.5076,"away_probability":0.4924,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:00:00+00:00","home_probability":0.5063,"away_probability":0.4937,"over_under":5.9,"projected_home_score":3.4,"projected_away_score":2.5,"bookmaker_count":18,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:06:00+00:00","home_probability":0.5032,"away_probability":0.4968,"over_under":6.0,"projected_home_score":3.8,"projected_away_score":2.2,"bookmaker_count":1,"probability_range":{"min":0.5032,"max":0.5032}},
{"timestamp":"2026-10-30T20:07:00+00:00","home_probability":0.5065,"away_probability":0.4935,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5152}},
{"timestamp":"2026-10-30T20:11:00+00:00","home_probability":0.5055,"away_probability":0.4945,"over_under":6.1,"projected_home_score":3.7,"projected_away_score":2.4,"bookmaker_count":11,"probability_range":{"min":0.5,"max":0.5152}}
],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{
"polymarket":[
{"timestamp":"2026-10-29T20:15:56.356074+00:00","home_probability":0.515,"away_probability":0.485,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-30T19:02:26.684116+00:00","home_probability":0.505,"away_probability":0.495,"draw_probability":null,"game_state":null}
],
"kalshi":[
{"timestamp":"2026-10-29T20:21:37.596394+00:00","home_probability":0.515,"away_probability":0.485,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-30T20:12:18.516253+00:00","home_probability":0.505,"away_probability":0.495,"draw_probability":null,"game_state":null}
]
},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":985},"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":552}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[
{"timestamp":"2026-10-29T21:58:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T21:59:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:00:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:03:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:04:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:05:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:06:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:07:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-29T22:08:00+00:00","home_probability":0.515},
{"timestamp":"2026-10-30T08:00:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:01:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:02:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:03:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:04:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:06:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:07:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:08:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T08:09:00+00:00","home_probability":0.525},
{"timestamp":"2026-10-30T20:00:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:03:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:04:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:06:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:07:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:09:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:11:00+00:00","home_probability":0.505},
{"timestamp":"2026-10-30T20:12:00+00:00","home_probability":0.505}
],
"blend_edge_pinned":true,
"blend_edge_observed_at":"2026-10-30T20:13:34.913575+00:00",
"blend_edge_fold_revision":{"15338496":2376},
"history_fold_revision":null,
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"kalshi":{"spread":-0.1,"home_margin":0.1,"confidence":0.85,"contracts":[{"threshold":-2.5,"probability":0.825},{"threshold":-1.5,"probability":0.725},{"threshold":1.5,"probability":0.295},{"threshold":2.5,"probability":0.19}]},"sportsbook":{"spread":-1.3,"home_margin":1.3,"confidence":1.0,"contracts":[]}},"implied_totals":{"kalshi":{"total":6.0,"confidence":0.9,"contracts":[{"threshold":1.5,"probability":0.985},{"threshold":2.5,"probability":0.97},{"threshold":3.5,"probability":0.865},{"threshold":4.5,"probability":0.785},{"threshold":5.5,"probability":0.55},{"threshold":6.5,"probability":0.445},{"threshold":7.5,"probability":0.25},{"threshold":8.5,"probability":0.175},{"threshold":9.5,"probability":0.075}]},"polymarket":{"total":6.1,"confidence":0.5,"contracts":[{"threshold":2.5,"probability":0.9715},{"threshold":3.5,"probability":0.865},{"threshold":8.5,"probability":0.175},{"threshold":9.5,"probability":0.075}]},"sportsbook":{"total":6.1,"confidence":1.0,"contracts":[]}},"projected_final":{"home_score":3.7,"away_score":2.4,"spread_source":"sportsbook","total_source":"sportsbook"}},
"points":62,
"bookmaker_count":19,
"snapshot_count":476,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##

    /// `probability-movement-v89/raw/nfl-pregame-detail.json`, BYTE FOR BYTE
    /// (sha256 1f81fa527d56660a7c3fb0b495b0a8489aa7b202a9cc200558c3b817940b0eb9; the Rams test
    /// re-hashes it). Rams vs Bills, scheduled 2026-10-13T00:15Z, captured 2026-10-12T05:45Z.
    private static let ramsDetail = ##"""
{"id":14780558,"external_id":"e6d00eedd87d367e510314bd8cab8f6f","sport":"americanfootball_nfl","sport_name":"NFL","home_team":"Los Angeles Rams","away_team":"Buffalo Bills","commence_time":"2026-10-13T00:15:00+00:00","start_is_tbd":false,"completed_at":null,"status":"scheduled","started_without_result":false,"home_score":null,"away_score":null,"home_team_data":{"team_id":544,"slug":"los-angeles-rams","primary_color":"#003594","secondary_color":"#ffd100","logo_small":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/lar.png","logo_large":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/lar.png","record":"2-2","abbreviation":"LAR","standings":{"pct":".500","ties":0,"wins":2,"losses":2,"streak":"W1","div_rank":3,"division":"NFC West","conference":"National Football Conference","home_record":"1-1","road_record":"1-1"}},"away_team_data":{"team_id":538,"slug":"buffalo-bills","primary_color":"#00338d","secondary_color":"#d50a0a","logo_small":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png","logo_large":"https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/buf.png","record":"3-1","abbreviation":"BUF","standings":{"pct":".750","ties":0,"wins":3,"losses":1,"streak":"L1","div_rank":1,"division":"AFC East","conference":"American Football Conference","home_record":"2-1","road_record":"1-0"}},"metadata":{"gender":"men","level":"professional","league":"NFL","importance":"regular_season"},"espn":{"espn_id":"401872994","broadcast":"ESPN, ABC","probability_sources":{"kalshi":0.615,"betting":0.614,"polymarket":0.615,"betting_book_count":11.0}},"win_probability_sources":{"kalshi":{"value":0.615,"display_name":"Kalshi","type":"market","color":"#22c55e","updated_at":"2026-10-12T05:44:33.447691+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031"},"betting":{"value":0.614,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-12T05:40:56.558654+00:00","evidence_status":"not_applicable"},"polymarket":{"value":0.615,"display_name":"Polymarket","type":"market","color":"#3b82f6","updated_at":"2026-10-12T05:45:00.084170+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031","price_evidence":"unproven"},"betting_book_count":{"value":11.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"event_tags":["class:pro_major","gender:men","importance:regular_season","league:nfl","level:professional","sport:football","status:scheduled","tier:1","timing:national_tv","timing:primetime"],"standings_context":{"home":"2-2, #3 NFC West","away":"3-1, #1 AFC East"},"current_odds":{"captured_at":"2026-10-12T04:37:03.501709+00:00","home_probability":0.615,"away_probability":0.385,"away_rendered_percent":38,"home_rendered_percent":62,"spread":-3.5,"over_under":54.4,"projected_home_score":29.0,"projected_away_score":25.4,"bookmaker_count":22},"bookmaker_odds":[{"bookmaker":"ballybet","home_moneyline":-177,"away_moneyline":145,"home_probability":0.6102,"away_probability":0.3898,"captured_at":"2026-10-11T11:30:46.854796+00:00","spread":-3.5,"over_under":54.0,"projected_home_score":28.8,"projected_away_score":25.2},{"bookmaker":"betanysports","home_moneyline":-180,"away_moneyline":155,"home_probability":0.6211,"away_probability":0.3789,"captured_at":"2026-10-11T11:30:46.902672+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"betmgm","home_moneyline":-185,"away_moneyline":150,"home_probability":0.6187,"away_probability":0.3813,"captured_at":"2026-10-12T04:06:08.526928+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":-173,"away_moneyline":152,"home_probability":0.6149,"away_probability":0.3851,"captured_at":"2026-10-12T04:06:08.512845+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betparx","home_moneyline":-177,"away_moneyline":145,"home_probability":0.6102,"away_probability":0.3898,"captured_at":"2026-10-11T11:30:46.842691+00:00","spread":-3.5,"over_under":54.0,"projected_home_score":28.8,"projected_away_score":25.2},{"bookmaker":"betrivers","home_moneyline":-177,"away_moneyline":145,"home_probability":0.6102,"away_probability":0.3898,"captured_at":"2026-10-12T04:06:08.519770+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betus","home_moneyline":-175,"away_moneyline":150,"home_probability":0.614,"away_probability":0.386,"captured_at":"2026-10-12T04:06:08.504581+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":-175,"away_moneyline":150,"home_probability":0.614,"away_probability":0.386,"captured_at":"2026-10-12T04:06:08.530318+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"courtside","home_moneyline":-176,"away_moneyline":153,"home_probability":0.6173,"away_probability":0.3827,"captured_at":"2026-10-11T21:54:03.736548+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"draftkings","home_moneyline":-175,"away_moneyline":145,"home_probability":0.6092,"away_probability":0.3908,"captured_at":"2026-10-12T04:37:03.455739+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"espnbet","home_moneyline":-175,"away_moneyline":150,"home_probability":0.614,"away_probability":0.386,"captured_at":"2026-10-11T21:54:27.431504+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"fanatics","home_moneyline":-175,"away_moneyline":145,"home_probability":0.6092,"away_probability":0.3908,"captured_at":"2026-10-12T04:37:03.501709+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-176,"away_moneyline":148,"home_probability":0.6126,"away_probability":0.3874,"captured_at":"2026-10-12T04:06:08.494089+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fliff","home_moneyline":-175,"away_moneyline":135,"home_probability":0.5993,"away_probability":0.4007,"captured_at":"2026-10-11T13:51:51.226636+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"hardrockbet","home_moneyline":-175,"away_moneyline":145,"home_probability":0.6092,"away_probability":0.3908,"captured_at":"2026-10-11T11:30:46.940574+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"hardrockbet_fl","home_moneyline":-175,"away_moneyline":145,"home_probability":0.6092,"away_probability":0.3908,"captured_at":"2026-10-11T11:30:46.935082+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"hardrockbet_oh","home_moneyline":-175,"away_moneyline":145,"home_probability":0.6092,"away_probability":0.3908,"captured_at":"2026-10-11T11:30:46.928015+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"lowvig","home_moneyline":-173,"away_moneyline":152,"home_probability":0.6149,"away_probability":0.3851,"captured_at":"2026-10-12T04:06:08.508141+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"mybookieag","home_moneyline":-186,"away_moneyline":150,"home_probability":0.6192,"away_probability":0.3808,"captured_at":"2026-10-12T04:06:08.501199+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"polymarket","home_moneyline":-163,"away_moneyline":156,"home_probability":0.6134,"away_probability":0.3866,"captured_at":"2026-10-08T08:35:27.709524+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"rebet","home_moneyline":-182,"away_moneyline":154,"home_probability":0.6211,"away_probability":0.3789,"captured_at":"2026-10-11T11:30:46.802372+00:00","spread":-3.5,"over_under":54.5,"projected_home_score":29.0,"projected_away_score":25.5},{"bookmaker":"williamhill_us","home_moneyline":-176,"away_moneyline":147,"home_probability":0.6117,"away_probability":0.3883,"captured_at":"2026-10-12T04:06:08.461562+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"hero_probability_observed_at":"2026-10-12T05:45:00.084170+00:00","blend_fold_revision":{"14780558":12497},"hero_probability":0.615,"hero_probability_away":0.385,"hero_probability_source":"blend","hero_sportsbook_count":11}
"""##

    /// A REDUCED VERBATIM SUBSET of `probability-movement-v89/raw/nfl-pregame-history.json`
    /// (488,773 bytes, sha256 c32ce4402faf5849afd93802eb4918d5b92a4d50f576bc2538c422f80d588332).
    /// Every top-level key, in source order, is the source's bytes, one key per line, except
    /// (0-based element indexes kept, in source order):
    ///   `history`            2 of 75: 0, 74
    ///   `bookmaker_history`  emptied to {}
    ///   `win_prob_history`   polymarket 0 of 146; kalshi 0 of 1157
    ///   `aggregate_line`     5 of 1143: 0, 831, 832, 1141, 1142 (1142 is the pinned edge)
    private static let ramsHistory = ##"""
{"event_id":14780558,
"home_team":"Los Angeles Rams",
"away_team":"Buffalo Bills",
"commence_time":"2026-10-13T00:15:00+00:00",
"completed_at":null,
"status":"scheduled",
"time_domain":{"start":"2026-10-11T05:45:00+00:00","end":"2026-10-12T05:45:12.645807+00:00","is_live":false,"min_window_seconds":1800},
"history":[{"timestamp":"2026-10-11T05:45:00+00:00","home_probability":0.6098,"away_probability":0.3902,"over_under":54.6,"projected_home_score":29.0,"projected_away_score":25.6,"bookmaker_count":21,"probability_range":{"min":0.5951,"max":0.6211}},{"timestamp":"2026-10-12T04:37:00+00:00","home_probability":0.6092,"away_probability":0.3908,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.6092,"max":0.6092}}],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{"polymarket":[{"timestamp":"2026-10-11T05:45:15.598351+00:00","home_probability":0.615,"away_probability":0.385,"draw_probability":null,"game_state":null}],"kalshi":[{"timestamp":"2026-10-11T05:45:42.061922+00:00","home_probability":0.615,"away_probability":0.385,"draw_probability":null,"game_state":null}]},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":146},"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":1157}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[{"timestamp":"2026-10-11T05:45:00+00:00","home_probability":0.615},{"timestamp":"2026-10-12T00:14:00+00:00","home_probability":0.6145},{"timestamp":"2026-10-12T00:15:00+00:00","home_probability":0.6145},{"timestamp":"2026-10-12T05:44:00+00:00","home_probability":0.615},{"timestamp":"2026-10-12T05:45:00+00:00","home_probability":0.615}],
"blend_edge_pinned":true,
"blend_edge_observed_at":"2026-10-12T05:45:00.084170+00:00",
"blend_edge_fold_revision":{"14780558":12497},
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"kalshi":{"spread":-3.2,"home_margin":3.2,"confidence":0.95,"contracts":[{"threshold":-14.5,"probability":0.915},{"threshold":-13.5,"probability":0.895},{"threshold":-10.5,"probability":0.865},{"threshold":-9.5,"probability":0.855},{"threshold":-7.5,"probability":0.825},{"threshold":-6.5,"probability":0.775},{"threshold":-5.5,"probability":0.765},{"threshold":-4.5,"probability":0.745},{"threshold":-3.5,"probability":0.725},{"threshold":-2.5,"probability":0.655},{"threshold":-1.5,"probability":0.635},{"threshold":1.5,"probability":0.585},{"threshold":2.5,"probability":0.565},{"threshold":3.5,"probability":0.475},{"threshold":4.5,"probability":0.435},{"threshold":5.5,"probability":0.425},{"threshold":6.5,"probability":0.385},{"threshold":7.5,"probability":0.325},{"threshold":9.5,"probability":0.285},{"threshold":10.5,"probability":0.265},{"threshold":13.5,"probability":0.215},{"threshold":14.5,"probability":0.175},{"threshold":16.5,"probability":0.165},{"threshold":17.5,"probability":0.135},{"threshold":20.5,"probability":0.095}]}},"implied_totals":{"kalshi":{"total":54.3,"confidence":0.9,"contracts":[{"threshold":33.5,"probability":0.945},{"threshold":36.5,"probability":0.915},{"threshold":39.5,"probability":0.875},{"threshold":42.5,"probability":0.815},{"threshold":45.5,"probability":0.745},{"threshold":48.5,"probability":0.675},{"threshold":51.5,"probability":0.585},{"threshold":52.5,"probability":0.56},{"threshold":53.5,"probability":0.525},{"threshold":54.5,"probability":0.495},{"threshold":55.5,"probability":0.455},{"threshold":56.5,"probability":0.425},{"threshold":57.5,"probability":0.405},{"threshold":60.5,"probability":0.325},{"threshold":63.5,"probability":0.255},{"threshold":66.5,"probability":0.195},{"threshold":69.5,"probability":0.145},{"threshold":72.5,"probability":0.105},{"threshold":75.5,"probability":0.075}]},"polymarket":{"total":54.2,"confidence":0.8,"contracts":[{"threshold":24.5,"probability":0.94},{"threshold":26.5,"probability":0.975},{"threshold":28.5,"probability":0.926},{"threshold":30.5,"probability":0.9345},{"threshold":32.5,"probability":0.9545},{"threshold":34.5,"probability":0.945},{"threshold":36.5,"probability":0.915},{"threshold":38.5,"probability":0.89},{"threshold":40.5,"probability":0.855},{"threshold":42.5,"probability":0.815},{"threshold":44.5,"probability":0.78},{"threshold":46.5,"probability":0.73},{"threshold":48.5,"probability":0.665},{"threshold":50.5,"probability":0.625},{"threshold":52.5,"probability":0.565},{"threshold":54.5,"probability":0.49},{"threshold":56.5,"probability":0.425},{"threshold":58.5,"probability":0.37},{"threshold":60.5,"probability":0.32},{"threshold":62.5,"probability":0.295},{"threshold":64.5,"probability":0.235},{"threshold":66.5,"probability":0.195},{"threshold":68.5,"probability":0.175},{"threshold":70.5,"probability":0.135},{"threshold":72.5,"probability":0.105},{"threshold":74.5,"probability":0.085}]}},"projected_final":{"home_score":28.8,"away_score":25.5,"spread_source":"kalshi","total_source":"kalshi"}},
"points":75,
"bookmaker_count":21,
"snapshot_count":793,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##
}
