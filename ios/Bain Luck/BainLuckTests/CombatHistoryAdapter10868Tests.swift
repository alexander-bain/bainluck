import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's adapter, part two (the two-fighter
/// win-probability history), on a REAL served body decoded exactly as the app
/// decodes it (`JSONDecoder` with `.convertFromSnakeCase`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED body, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///
/// - `mmaHistory` — a REDUCED VERBATIM SUBSET of
///   `additional-match-v146/raw/mma-event-history.json` (610,065 bytes, sha256
///   fa831fb6d396abba72a7ef7dc5e58b66b6b8f26baf50ae7ee058066f7edaf6fb; the same
///   bytes are retained under 97 capture directories, served by
///   `GET /api/events/15318681/history`). Every top-level key, in source order,
///   is the source's bytes, except (0-based element indexes kept, in source
///   order, one per line):
///     `history`            4 of 120: 0, 110, 117, 119
///     `bookmaker_history`  emptied to {}
///     `win_prob_history`   kalshi 0, 2262, 2274, 2280 of 2281
///     `aggregate_line`     31 of 2348: 0, 1, 1809–1812, 2254, 2255, 2325–2347
///   Generated and checked by `/tmp/cli-10868-combat/make_subsets.py` (kept
///   outside the repo): every kept element is a verbatim substring of its
///   source, and the parsed subset equals the selected elements key by key.
///   The served blend is home-only and its last row (00:37Z, 0.5713) is the
///   server's pinned hero edge (`blend_edge_pinned: true`).
/// - the event — part one's `mmaDetail`, byte for byte
///   (`CombatBoutPageAdapter10868Tests`, sha256 there).
///
/// WHAT A SUBSET CHANGES. Rows left out are absent; the block that carries the
/// boundary claims is kept whole: 00:12–00:37Z around the 00:20Z start.
///
/// CONSTRUCTED here, each named where used and changing only the key it names
/// in the DETAIL body (the history subset is never edited): the reader's
/// calendar and `now`; a before variant (`commence_time` 01:00Z, read at
/// 00:43Z); a final variant (`status: completed`); an unconfirmed start
/// (`start_is_tbd: true`). Clock words are the adapter's own.
@MainActor
final class CombatHistoryAdapter10868Tests: XCTestCase {
    private typealias H = CombatHistoryAdapter10868
    private typealias Fixtures = CombatBoutPageAdapter10868Tests

    private func host(_ now: String) -> H.Host {
        H.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    static func response() throws -> EventHistoryResponse {
        try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(Self.mmaHistory.utf8))
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    /// The around-start block, rows 2331–2346 (00:18Z–00:36Z): the last
    /// pre-fight row, then the fight's rows. 2347 is the pinned edge.
    private let fightRows: [(String, Double)] = [
        ("2026-10-04T00:18:00+00:00", 0.6724), ("2026-10-04T00:20:00+00:00", 0.6724),
        ("2026-10-04T00:21:00+00:00", 0.6724), ("2026-10-04T00:22:00+00:00", 0.6767),
        ("2026-10-04T00:23:00+00:00", 0.6767), ("2026-10-04T00:24:00+00:00", 0.6806),
        ("2026-10-04T00:25:00+00:00", 0.6757), ("2026-10-04T00:26:00+00:00", 0.7485),
        ("2026-10-04T00:27:00+00:00", 0.683), ("2026-10-04T00:28:00+00:00", 0.5835),
        ("2026-10-04T00:29:00+00:00", 0.5356), ("2026-10-04T00:31:00+00:00", 0.5356),
        ("2026-10-04T00:33:00+00:00", 0.5356), ("2026-10-04T00:34:00+00:00", 0.5356),
        ("2026-10-04T00:35:00+00:00", 0.5356), ("2026-10-04T00:36:00+00:00", 0.6801),
    ]

    // MARK: - Fixture

    func testTheSubsetDecodesAsTheServedBlendWithItsPinnedEdge() throws {
        let response = try Self.response()
        XCTAssertEqual(response.eventId, 15318681)
        XCTAssertEqual(response.status, "suspended")
        XCTAssertEqual(response.aggregateLine?.count, 31)
        XCTAssertEqual(response.history.count, 4)
        XCTAssertEqual(response.blendEdgePinned, true)
        XCTAssertEqual(response.commenceTimeIsKickoff, true)
        XCTAssertEqual(response.evidenceContract?.readableResolution, 300)
        XCTAssertTrue(try XCTUnwrap(response.aggregateLine).allSatisfy { $0.awayProbability == nil },
                      "the served blend is home-only: the away trace is the complement, labelled as such")
        XCTAssertEqual(H.Rows.line(response), .blend)
        XCTAssertEqual(response.aggregateLine?.last?.timestamp, "2026-10-04T00:37:00+00:00")
    }

    // MARK: - During (the retained state)

    func testDuringDrawsTheLastPreFightRowThenTheFightAndNeverThePinnedEdge() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        let input = H.history(try Self.response(), event: event, phase: .during, host: reader)
        let home = input.series[0]
        let away = input.series[1]
        XCTAssertEqual(home.id, "blend:15318681:home")
        XCTAssertEqual(home.name, "Ateba Gautier")
        XCTAssertEqual(home.shape, .circle)
        XCTAssertEqual(away.id, "blend:15318681:away")
        XCTAssertEqual(away.name, "Roman Kopylov")
        XCTAssertEqual(away.shape, .diamond)

        // One run: in-fight intervals are 60–120 s, far under the chart's 600 s floor.
        XCTAssertEqual(home.runs.count, 1)
        let points = home.runs[0].points
        XCTAssertEqual(points.map(\.x), fightRows.map { x($0.0) })
        XCTAssertEqual(points.map(\.probability), fightRows.map(\.1))
        XCTAssertEqual(points.first?.style, .hollow)
        XCTAssertEqual(points.filter { $0.style == .hollow }.count, 1, "only the last pre-fight row is hollow")
        XCTAssertFalse(points.contains { $0.x == x("2026-10-04T00:37:00+00:00") },
                       "the pinned hero edge is not a recorded reading")

        // The away trace is the same rows' complement — never an extra point.
        let others = away.runs.flatMap(\.points)
        XCTAssertEqual(others.map(\.x), points.map(\.x))
        XCTAssertEqual(others.map(\.probability), points.map { 1 - $0.probability })
        let complement = "Roman Kopylov is the other side of the same blend: 100% − Ateba Gautier."
        XCTAssertEqual(input.notes, ["Source: Bain Luck", complement, "Gaps remain blank."])
        XCTAssertTrue(input.summary.hasSuffix(complement))

        let pregame = "2026-10-04T00:18:00+00:00"
        let latest = "2026-10-04T00:36:00+00:00"
        XCTAssertEqual(input.readout, .beforeAndRecorded(beforeLabel: "Pre-fight", recordedLabel: "Recorded"))
        XCTAssertEqual(home.before, .observation(pointID: "blend:15318681:home#\(pregame)", figure: "67%",
                                                 provenance: "Last pre-fight · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(away.before, .observation(pointID: "blend:15318681:away#\(pregame)", figure: "33%",
                                                 provenance: "Last pre-fight · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(home.recorded, .observation(pointID: "blend:15318681:home#\(latest)", figure: "68%",
                                                   provenance: "Recorded \(H.clockWords(latest.asDate!, host: reader))"))
        XCTAssertEqual(away.recorded, .observation(pointID: "blend:15318681:away#\(latest)", figure: "32%",
                                                   provenance: "Recorded \(H.clockWords(latest.asDate!, host: reader))"))
        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x(pregame), upper: x(latest)))
        XCTAssertEqual(input.guides, [], "the combat bodies serve no period or scoring guide; none is invented")
        XCTAssertEqual(input.caption, "Fight history")
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: "Hollow · last pre-fight", filled: nil))
        XCTAssertEqual(input.inspect?.isAvailable, false)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.expand?.id, "history.expand")
        XCTAssertNil(input.inspection)
        XCTAssertNil(input.plotAbsence)
    }

    // MARK: - Before (constructed)

    func testBeforeDrawsOneDayOfPreFightRowsToTheLastOneAndNoRecordedSlot() throws {
        // CONSTRUCTED: the detail's `commence_time` moved to 01:00Z, read at 00:43Z.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["commence_time": "2026-10-04T01:00:00+00:00"])
        let input = H.history(try Self.response(), event: event, phase: .before, host: host("2026-10-04T00:43:00Z"))
        let points = input.series[0].runs.flatMap(\.points)
        XCTAssertEqual(input.series[0].runs.count, 1, "pre-fight intervals are never judged")
        XCTAssertEqual(points.count, 28)
        XCTAssertEqual(points.first?.x, x("2026-10-03T00:54:00+00:00"),
                       "the frame opens one day before the last pre-fight reading (00:36), not before the start")
        XCTAssertTrue(points.contains { $0.x == x("2026-10-03T00:58:00+00:00") },
                      "inside the last reading's day, though older than the start less one day")
        XCTAssertFalse(points.contains { $0.x < x("2026-10-04T00:36:00+00:00") - HockeyJourneyHistoryAdapter10868.beforeWindow },
                       "the September 20 rows stay outside the day")
        XCTAssertEqual(points.last?.x, x("2026-10-04T00:36:00+00:00"))
        XCTAssertEqual(points.last?.style, .hollow)
        XCTAssertEqual(input.readout, .singleBefore(label: "Pre-fight"))
        XCTAssertEqual(input.series[0].recorded, .absent(words: "Not recorded"))
        XCTAssertEqual(input.caption, "Before the fight")
        XCTAssertNil(input.inspect)
    }

    // MARK: - Final (constructed)

    func testTheFinalKeepsTheSameRecordedRowsWithASinglePreFightReadout() throws {
        // CONSTRUCTED: the detail's `status: completed`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "completed"])
        let input = H.history(try Self.response(), event: event, phase: .final, host: host(Fixtures.readAt))
        let points = input.series[0].runs.flatMap(\.points)
        XCTAssertEqual(points.map(\.x), fightRows.map { x($0.0) })
        XCTAssertEqual(input.readout, .singleBefore(label: "Pre-fight"))
        XCTAssertEqual(input.series[0].recorded, .absent(words: "Not recorded"))
        XCTAssertNil(input.inspect)
        XCTAssertFalse(points.contains { $0.probability == 1 || $0.probability == 0 },
                       "no result is drawn as a reading")
    }

    // MARK: - Unconfirmed start (constructed)

    func testAnUnconfirmedStartDrawsEveryRecordedRowUnsplitAndSaysSo() throws {
        // CONSTRUCTED: the detail's `start_is_tbd: true`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["start_is_tbd": true])
        let input = H.history(try Self.response(), event: event, phase: .during, host: host(Fixtures.readAt))
        let home = input.series[0]
        XCTAssertEqual(home.runs.count, 1)
        XCTAssertEqual(home.runs[0].points.count, 30, "every readable row but the pinned edge")
        XCTAssertTrue(home.runs[0].points.allSatisfy { $0.style == .filled }, "no row is called pre-fight")
        XCTAssertEqual(input.readout, .singleBefore(label: "Start time not confirmed"))
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
        XCTAssertEqual(home.before, .absent(words: H.Words.unconfirmedStartWords))
        XCTAssertEqual(input.guides, [])
    }

    // MARK: - No response

    func testNoHistoryResponseSaysHistoryUnavailableAndOffersNoWorkingControl() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let chart = H.unavailable(event: event, phase: .during)
        XCTAssertEqual(chart.plotAbsence?.title, "History unavailable")
        XCTAssertEqual(chart.summary, "History unavailable")
        XCTAssertTrue(chart.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertEqual(chart.series.map(\.shape), [.circle, .diamond])
        XCTAssertTrue(chart.notes.isEmpty)
        XCTAssertNil(chart.expand)
        XCTAssertNil(chart.inspect)
        XCTAssertEqual(chart.details?.isAvailable, false)
    }

    // MARK: - Another event's history

    /// CONSTRUCTED: the retained subset with only `event_id` changed to a
    /// different event's id. None of it is drawn: the chart reads exactly as with
    /// no response. The same body under its own id still draws.
    func testAnotherEventsHistoryDrawsNothingAndReadsAsUnavailable() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        let foreign = H.history(try Self.response(eventId: 15318682), event: event, phase: .during, host: reader)
        XCTAssertEqual(foreign, H.unavailable(event: event, phase: .during))
        XCTAssertTrue(foreign.series.allSatisfy { $0.runs.isEmpty && $0.links.isEmpty })
        XCTAssertNil(foreign.expand)
        XCTAssertNil(foreign.inspect)
        XCTAssertFalse(H.history(try Self.response(), event: event, phase: .during, host: reader).series[0].runs.isEmpty)
    }

    /// CONSTRUCTED: the retained subset with only `event_id` replaced.
    static func response(eventId: Int) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(Self.mmaHistory.utf8)) as? [String: Any])
        object["event_id"] = eventId
        return try Fixtures.decoder().decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    // MARK: - Retained body (reduced verbatim subset)

    static let mmaHistory = ##"""
{"event_id":15318681,
"home_team":"Ateba Gautier",
"away_team":"Roman Kopylov",
"commence_time":"2026-10-04T00:20:00+00:00",
"completed_at":null,
"status":"suspended",
"time_domain":{"start":"2026-09-20T04:46:00+00:00","end":"2026-10-11T23:32:27.443365+00:00","is_live":false,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-09-25T12:06:00+00:00","home_probability":0.6345,"away_probability":0.3655,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":1,"probability_range":{"min":0.6345,"max":0.6345}},
{"timestamp":"2026-10-03T23:59:00+00:00","home_probability":0.6724,"away_probability":0.3276,"over_under":1.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.669,"max":0.6757}},
{"timestamp":"2026-10-04T00:29:00+00:00","home_probability":0.5356,"away_probability":0.4644,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.5,"max":0.5713}},
{"timestamp":"2026-10-04T00:37:00+00:00","home_probability":0.6801,"away_probability":0.3199,"over_under":2.0,"projected_home_score":3.0,"projected_away_score":-0.5,"bookmaker_count":2,"probability_range":{"min":0.6767,"max":0.6834}}
],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{"kalshi":[
{"timestamp":"2026-09-20T04:46:00+00:00","home_probability":0.45,"away_probability":0.55,"draw_probability":null,"game_state":null,"evidence":{"kind":"candle"}},
{"timestamp":"2026-10-04T00:18:29.947229+00:00","home_probability":0.315,"away_probability":0.685,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-04T00:28:55.329890+00:00","home_probability":0.995,"away_probability":0.005,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-04T00:35:45.679197+00:00","home_probability":0.99,"away_probability":0.01,"draw_probability":null,"game_state":null}
]},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":2281}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[
{"timestamp":"2026-09-20T04:46:00+00:00","home_probability":0.45},
{"timestamp":"2026-09-20T05:03:00+00:00","home_probability":0.455},
{"timestamp":"2026-10-03T00:54:00+00:00","home_probability":0.6778},
{"timestamp":"2026-10-03T00:58:00+00:00","home_probability":0.6778},
{"timestamp":"2026-10-03T01:01:00+00:00","home_probability":0.6778},
{"timestamp":"2026-10-03T01:05:00+00:00","home_probability":0.6778},
{"timestamp":"2026-10-03T22:40:00+00:00","home_probability":0.6729},
{"timestamp":"2026-10-03T22:41:00+00:00","home_probability":0.6729},
{"timestamp":"2026-10-04T00:12:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:13:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:14:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:15:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:16:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:17:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:18:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:20:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:21:00+00:00","home_probability":0.6724},
{"timestamp":"2026-10-04T00:22:00+00:00","home_probability":0.6767},
{"timestamp":"2026-10-04T00:23:00+00:00","home_probability":0.6767},
{"timestamp":"2026-10-04T00:24:00+00:00","home_probability":0.6806},
{"timestamp":"2026-10-04T00:25:00+00:00","home_probability":0.6757},
{"timestamp":"2026-10-04T00:26:00+00:00","home_probability":0.7485},
{"timestamp":"2026-10-04T00:27:00+00:00","home_probability":0.683},
{"timestamp":"2026-10-04T00:28:00+00:00","home_probability":0.5835},
{"timestamp":"2026-10-04T00:29:00+00:00","home_probability":0.5356},
{"timestamp":"2026-10-04T00:31:00+00:00","home_probability":0.5356},
{"timestamp":"2026-10-04T00:33:00+00:00","home_probability":0.5356},
{"timestamp":"2026-10-04T00:34:00+00:00","home_probability":0.5356},
{"timestamp":"2026-10-04T00:35:00+00:00","home_probability":0.5356},
{"timestamp":"2026-10-04T00:36:00+00:00","home_probability":0.6801},
{"timestamp":"2026-10-04T00:37:00+00:00","home_probability":0.5713}
],
"blend_edge_pinned":true,
"blend_edge_observed_at":"2026-10-04T00:42:55.271003+00:00",
"blend_edge_fold_revision":{"15318681":1760,"15318406":0,"15315711":1480},
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"sportsbook":{"spread":-3.5,"home_margin":3.5,"confidence":1.0,"contracts":[]}},"implied_totals":{"sportsbook":{"total":2.0,"confidence":1.0,"contracts":[]}},"projected_final":null},
"points":120,
"bookmaker_count":7,
"snapshot_count":291,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##
}
