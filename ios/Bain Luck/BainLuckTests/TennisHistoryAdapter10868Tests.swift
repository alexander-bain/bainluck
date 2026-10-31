import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's adapter, part two (the two-player
/// win-probability history), on REAL served bodies decoded exactly as the app
/// decodes them (`JSONDecoder` with `.convertFromSnakeCase`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/accessible-chart-inspection-v90/raw/`:
///
/// - `liveHistory` — a REDUCED VERBATIM SUBSET of `tennis-15327807-history.json`
///   (286,494 bytes, sha256 85e6881b43b33dbeb400fc3949c9fb5b6619ac4e463d37679384f772322a1ba9,
///   served by `GET /api/events/15327807/history`). Every top-level key, in
///   source order, is the source's bytes, except (0-based element indexes kept,
///   in source order, one per line):
///     `history`            4 of 113: 0, 1, 111, 112
///     `bookmaker_history`  emptied to {}
///     `win_prob_history`   kalshi 0, 396 of 397; polymarket 0, 277 of 278
///     `aggregate_line`     106 of 601: 0, 1, 19, 20, 21, 500–600
///   The served blend is home-only. Its last row (12:24:06Z) is the server's
///   pinned hero edge (`blend_edge_pinned: true`), and the minute 12:24 holds
///   only Kalshi's carried-forward live edge (kalshi 396), so rows 599 and 600
///   are not readings.
/// - `finalHistory` — a REDUCED VERBATIM SUBSET of `tennis-15327291-history.json`
///   (526,094 bytes, sha256 57cce1ef84f4bb100a02b72dc88196006016c36b42f119bef4e49378f27c9df2):
///     `history`            4 of 213: 0, 1, 211, 212
///     `bookmaker_history`  emptied to {}
///     `win_prob_history`   polymarket 0, 592 of 593; kalshi 0, 769 of 770
///     `aggregate_line`     46 of 902: 0, 705–725, 878–901
///   The blend kept quoting after the match ended (15:41–16:07Z), and its last
///   served row is the settlement (15:40Z, 1.0), served out of time order.
///   Generated and checked by `/tmp/cli-10868-tennis/make_subsets.py` (kept
///   outside the repo): every kept element is a verbatim substring of its
///   source, and the parsed subset equals the selected elements key by key.
/// - the events — part one's `liveDetail` and `finalDetail`, byte for byte
///   (`TennisMatchPageAdapter10868Tests`, sha256 there).
///
/// WHAT A SUBSET CHANGES. Rows left out are absent. The live in-play block is
/// kept whole (10:54–12:24Z), so the live chart is one run. The final keeps
/// 12:44–13:00Z and 15:33–16:07Z only; the rows between are absent, so the
/// final chart breaks there rather than joining across them — that break is the
/// subset's, and it is asserted as the chart's own rule, not as the match.
/// Pre-start intervals are never judged by the chart's gap rule, so the 20-hour
/// pre-match span the live subset leaves out is not a break.
///
/// CONSTRUCTED here, each named where used and changing only the key it names
/// in the DETAIL body (the history subsets are never edited): the reader's
/// calendar and `now`; a before variant (`status: scheduled`, `commence_time`
/// 13:00Z, read at 12:24:30Z); an unconfirmed start (`start_is_tbd: true`).
/// Clock words are the adapter's own.
@MainActor
final class TennisHistoryAdapter10868Tests: XCTestCase {
    private typealias H = TennisHistoryAdapter10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests

    private func host(_ now: String) -> H.Host {
        H.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    static func live() throws -> EventHistoryResponse {
        try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(Self.liveHistory.utf8))
    }

    static func finished() throws -> EventHistoryResponse {
        try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(Self.finalHistory.utf8))
    }

    /// CONSTRUCTED: the live subset with ONLY its `event_id` changed to the
    /// final's (15327291) — another event's body arriving on this page.
    static func foreign() throws -> EventHistoryResponse {
        let own = "{\"event_id\":15327807,"
        XCTAssertTrue(liveHistory.hasPrefix(own))
        let body = liveHistory.replacingOccurrences(of: own, with: "{\"event_id\":15327291,")
        return try Fixtures.decoder().decode(EventHistoryResponse.self, from: Data(body.utf8))
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    /// The blend's complement pair for one home value, through the app's own
    /// two-outcome display rule (the figure the history prints for that row).
    private func pair(_ home: Double) -> (away: String, home: String) {
        duelProbabilityStrings(away: 1 - home, home: home, complementaryAway: true)
    }

    // MARK: - Fixtures

    func testTheSubsetsDecodeAsTheServedBlend() throws {
        let live = try Self.live()
        XCTAssertEqual(live.eventId, 15327807)
        XCTAssertEqual(live.status, "live")
        XCTAssertEqual(live.aggregateLine?.count, 106)
        XCTAssertEqual(live.blendEdgePinned, true)
        XCTAssertEqual(live.commenceTimeIsKickoff, true)
        XCTAssertEqual(H.Rows.line(live), .blend)
        XCTAssertTrue(try XCTUnwrap(live.aggregateLine).allSatisfy { $0.awayProbability == nil },
                      "the served blend is home-only: the away trace is the complement, labelled as such")
        let finished = try Self.finished()
        XCTAssertEqual(finished.eventId, 15327291)
        XCTAssertEqual(finished.aggregateLine?.count, 46)
        XCTAssertEqual(finished.blendEdgePinned, false)
        XCTAssertEqual(finished.aggregateLine?.last?.timestamp, "2026-10-11T15:40:00+00:00")
        XCTAssertEqual(finished.aggregateLine?.last?.homeProbability, 1.0)
        XCTAssertEqual(H.Rows.line(finished), .blend)
    }

    // MARK: - During (the retained live state)

    func testDuringDrawsTheLastReadingBeforeTheScheduledStartThenTheMatchAndNoCarriedOrPinnedRow() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let reader = host(Fixtures.liveReadAt)
        let input = H.history(try Self.live(), event: event, phase: .during, host: reader)
        let home = input.series[0]
        let away = input.series[1]
        XCTAssertEqual(home.id, "blend:15327807:home")
        XCTAssertEqual(home.name, "Arthur Fils")
        XCTAssertEqual(home.shape, .circle)
        XCTAssertEqual(away.id, "blend:15327807:away")
        XCTAssertEqual(away.name, "Botic van de Zandschulp")
        XCTAssertEqual(away.shape, .diamond)

        // One run: the in-play rows are 60 s apart, far under the chart's 600 s floor.
        XCTAssertEqual(home.runs.count, 1)
        let points = home.runs[0].points
        XCTAssertEqual(points.count, 89, "rows 510–598")
        XCTAssertEqual(points.first?.x, x("2026-10-12T10:54:00+00:00"))
        XCTAssertEqual(points.first?.probability, 0.795)
        XCTAssertEqual(points.first?.style, .hollow)
        XCTAssertEqual(points.filter { $0.style == .hollow }.count, 1, "only the last reading before the start is hollow")
        XCTAssertEqual(points.last?.x, x("2026-10-12T12:23:00+00:00"))
        XCTAssertEqual(points.last?.probability, 0.203605)
        XCTAssertFalse(points.contains { $0.x == x("2026-10-12T12:24:00+00:00") },
                       "the carried-forward minute is not a recorded reading")
        XCTAssertFalse(points.contains { $0.x == x("2026-10-12T12:24:06.030278+00:00") },
                       "the pinned hero edge is not a recorded reading")

        // The away trace is the same rows' complement — never an extra point.
        let others = away.runs.flatMap(\.points)
        XCTAssertEqual(others.map(\.x), points.map(\.x))
        XCTAssertEqual(others.map(\.probability), points.map { 1 - $0.probability })
        let complement = "Botic van de Zandschulp is the other side of the same blend: 100% − Arthur Fils."
        XCTAssertEqual(input.notes, ["Source: Bain Luck", complement, "Gaps remain blank."])
        XCTAssertTrue(input.summary.hasSuffix(complement))

        let pregame = "2026-10-12T10:54:00+00:00"
        let latest = "2026-10-12T12:23:00+00:00"
        XCTAssertEqual(input.readout, .beforeAndRecorded(beforeLabel: "Before scheduled start",
                                                         recordedLabel: "Recorded chance"))
        XCTAssertEqual(home.before, .observation(pointID: "blend:15327807:home#\(pregame)", figure: pair(0.795).home,
                                                 provenance: "Before scheduled start · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(away.before, .observation(pointID: "blend:15327807:away#\(pregame)", figure: pair(0.795).away,
                                                 provenance: "Before scheduled start · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(home.recorded, .observation(pointID: "blend:15327807:home#\(latest)", figure: "20%",
                                                   provenance: "Recorded chance · \(H.clockWords(latest.asDate!, host: reader))"))
        XCTAssertEqual(away.recorded, .observation(pointID: "blend:15327807:away#\(latest)", figure: "80%",
                                                   provenance: "Recorded chance · \(H.clockWords(latest.asDate!, host: reader))"))
        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x(pregame), upper: x(latest)))
        XCTAssertEqual(input.guides, [], "the tennis bodies serve no period or scoring guide; none is invented")
        XCTAssertEqual(input.caption, "Match history")
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: "Hollow · before scheduled start", filled: nil))
        XCTAssertEqual(input.inspect?.isAvailable, false)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.expand?.id, "history.expand")
        XCTAssertNil(input.inspection)
        XCTAssertNil(input.plotAbsence)
    }

    // MARK: - Final (retained)

    func testTheFinalDrawsNoSettlementAndNothingAfterTheMatchEnded() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let reader = host(Fixtures.finalReadAt)
        let input = H.history(try Self.finished(), event: event, phase: .final, host: reader)
        let home = input.series[0]

        // The subset leaves out rows 726–877, so the chart breaks there rather
        // than joining across the absent span.
        XCTAssertEqual(home.runs.count, 2)
        let opening = ["12:49", "12:50", "12:51", "12:52", "12:53", "12:54", "12:55", "12:56", "12:57", "12:58",
                       "12:59", "13:00"]
        let closing = ["15:33", "15:34", "15:35", "15:36", "15:37", "15:38", "15:39", "15:40"]
        XCTAssertEqual(home.runs[0].points.map(\.x), opening.map { x("2026-10-11T\($0):00+00:00") })
        XCTAssertEqual(home.runs[1].points.map(\.x), closing.map { x("2026-10-11T\($0):00+00:00") })
        XCTAssertEqual(home.runs[1].points.last?.probability, 0.891273)
        let points = home.runs.flatMap(\.points)
        XCTAssertFalse(points.contains { $0.probability == 1 || $0.probability == 0 },
                       "the settlement row is the result, never a reading")
        let end = try XCTUnwrap(try Self.finished().completedAt?.asDate)
        XCTAssertFalse(points.contains { $0.x > end.timeIntervalSince1970 },
                       "the blend's rows after the match ended (15:41–16:07Z) are not drawn")

        XCTAssertEqual(input.readout, .singleBefore(label: "Before scheduled start"))
        let pregame = "2026-10-11T12:49:00+00:00"
        XCTAssertEqual(home.before, .observation(pointID: "blend:15327291:home#\(pregame)", figure: "46%",
                                                 provenance: "Before scheduled start · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(input.series[1].before, .observation(pointID: "blend:15327291:away#\(pregame)", figure: "54%",
                                                            provenance: "Before scheduled start · \(H.clockWords(pregame.asDate!, host: reader))"))
        XCTAssertEqual(home.recorded, .absent(words: "Not recorded"))
        XCTAssertEqual(input.caption, "Match history")
        XCTAssertNil(input.inspect)
    }

    // MARK: - Before (constructed)

    func testBeforeDrawsOneDayOfReadingsToTheLastOneAndNoRecordedSlot() throws {
        // CONSTRUCTED: the detail's `status: scheduled` and `commence_time` 13:00Z, read at 12:24:30Z.
        let event = try Fixtures.edited(Fixtures.liveDetail, ["status": "scheduled",
                                                              "commence_time": "2026-10-12T13:00:00+00:00"])
        let input = H.history(try Self.live(), event: event, phase: .before, host: host(Fixtures.liveReadAt))
        let points = input.series[0].runs.flatMap(\.points)
        XCTAssertEqual(input.series[0].runs.count, 1, "intervals before the start are never judged")
        XCTAssertEqual(points.count, 104)
        XCTAssertEqual(points.first?.x, x("2026-10-11T12:24:00+00:00"),
                       "the frame opens one day before the last reading (12:23), not before the scheduled start")
        XCTAssertTrue(points.contains { $0.x == x("2026-10-11T12:59:00+00:00") },
                      "inside the last reading's day, though older than the start less one day")
        XCTAssertFalse(points.contains { $0.x < x("2026-10-12T12:23:00+00:00") - HockeyJourneyHistoryAdapter10868.beforeWindow },
                       "never older than one day before the last reading")
        XCTAssertEqual(points.last?.x, x("2026-10-12T12:23:00+00:00"))
        XCTAssertEqual(points.last?.style, .hollow)
        XCTAssertEqual(input.readout, .singleBefore(label: "Before scheduled start"))
        XCTAssertEqual(input.series[0].recorded, .absent(words: "Not recorded"))
        XCTAssertEqual(input.caption, "Before the match")
        XCTAssertEqual(input.guides, [])
        XCTAssertNil(input.inspect)
    }

    // MARK: - Unconfirmed start (constructed)

    func testAnUnconfirmedStartDrawsEveryRecordedRowUnsplitAndSaysSo() throws {
        // CONSTRUCTED: the detail's `start_is_tbd: true`.
        let event = try Fixtures.edited(Fixtures.liveDetail, ["start_is_tbd": true])
        let input = H.history(try Self.live(), event: event, phase: .during, host: host(Fixtures.liveReadAt))
        let home = input.series[0]
        XCTAssertEqual(home.runs.count, 1)
        XCTAssertEqual(home.runs[0].points.count, 104, "every readable row but the carried minute and the pinned edge")
        XCTAssertTrue(home.runs[0].points.allSatisfy { $0.style == .filled }, "no row is called before the start")
        XCTAssertEqual(input.readout, .singleBefore(label: "Start time not confirmed"))
        XCTAssertEqual(input.markKey, FieldHistoryMarkKey10868(hollow: nil, filled: nil))
        XCTAssertEqual(home.before, .absent(words: H.Words.unconfirmedStartWords))
        XCTAssertEqual(input.guides, [])
    }

    // MARK: - Event identity

    func testAForeignHistoryIsRefusedWholeAndTheSameEventIsUnchanged() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let reader = host(Fixtures.liveReadAt)
        let live = try Self.live()
        XCTAssertEqual(H.admitted(live, for: event), live)
        XCTAssertNil(H.admitted(nil, for: event))
        XCTAssertEqual(H.history(live, event: event, phase: .during, host: reader).series[0].runs.first?.points.count, 89,
                       "this event's own body is drawn exactly as before")

        let foreign = try Self.foreign()
        XCTAssertEqual(foreign.eventId, 15327291)
        XCTAssertNil(H.admitted(foreign, for: event))
        let refused = H.history(foreign, event: event, phase: .during, host: reader)
        XCTAssertEqual(refused, H.unavailable(event: event, phase: .during),
                       "another event's rows are never this match's plot, baseline or reading")
        XCTAssertEqual(refused.plotAbsence?.title, "History unavailable")
        XCTAssertTrue(refused.series.allSatisfy { $0.runs.isEmpty })
        XCTAssertEqual(refused.series.map(\.name), ["Arthur Fils", "Botic van de Zandschulp"], "this page's own players")
        XCTAssertNil(refused.expand)
        XCTAssertNil(refused.inspect)
    }

    // MARK: - No response

    func testNoHistoryResponseSaysHistoryUnavailableAndOffersNoWorkingControl() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
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

    // MARK: - Retained bodies (reduced verbatim subsets)

    static let liveHistory = ##"""
{"event_id":15327807,
"home_team":"Arthur Fils",
"away_team":"Botic van de Zandschulp",
"commence_time":"2026-10-12T10:55:00+00:00",
"completed_at":null,
"status":"live",
"time_domain":{"start":"2026-10-12T10:55:00+00:00","end":"2026-10-12T12:24:06.030278+00:00","is_live":true,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-10-11T12:24:00+00:00","home_probability":0.7807,"away_probability":0.2193,"over_under":21.6,"projected_home_score":12.9,"projected_away_score":8.8,"bookmaker_count":8,"probability_range":{"min":0.7746,"max":0.7874}},
{"timestamp":"2026-10-11T14:08:00+00:00","home_probability":0.7792,"away_probability":0.2208,"over_under":21.6,"projected_home_score":12.9,"projected_away_score":8.8,"bookmaker_count":4,"probability_range":{"min":0.7758,"max":0.7864}},
{"timestamp":"2026-10-12T12:22:00+00:00","home_probability":0.2319,"away_probability":0.7681,"over_under":22.5,"projected_home_score":9.5,"projected_away_score":13.0,"bookmaker_count":5,"probability_range":{"min":0.1912,"max":0.3535}},
{"timestamp":"2026-10-12T12:23:00+00:00","home_probability":0.2019,"away_probability":0.7982,"over_under":22.5,"projected_home_score":9.5,"projected_away_score":13.0,"bookmaker_count":4,"probability_range":{"min":0.1912,"max":0.2129}}
],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{"kalshi":[
{"timestamp":"2026-10-11T12:25:36.264609+00:00","home_probability":0.795,"away_probability":0.205,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-12T12:24:06+00:00","home_probability":0.795,"away_probability":0.205,"draw_probability":null,"game_state":null,"live_edge":true,"evidence":{"kind":"live_edge"}}
],"polymarket":[
{"timestamp":"2026-10-11T12:33:35.370733+00:00","home_probability":0.795,"away_probability":0.205,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-12T12:23:45.310277+00:00","home_probability":0.21,"away_probability":0.79,"draw_probability":null,"game_state":null}
]},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":397},"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":278}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[
{"timestamp":"2026-10-11T12:24:00+00:00","home_probability":0.7807},
{"timestamp":"2026-10-11T12:25:00+00:00","home_probability":0.7807},
{"timestamp":"2026-10-11T12:59:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-11T13:00:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-11T13:01:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:37:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:39:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:40:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:45:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:46:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:47:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:48:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:49:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:51:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:53:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:54:00+00:00","home_probability":0.795},
{"timestamp":"2026-10-12T10:56:00+00:00","home_probability":0.786711},
{"timestamp":"2026-10-12T10:57:00+00:00","home_probability":0.793395},
{"timestamp":"2026-10-12T10:58:00+00:00","home_probability":0.794447},
{"timestamp":"2026-10-12T10:59:00+00:00","home_probability":0.804211},
{"timestamp":"2026-10-12T11:00:00+00:00","home_probability":0.797553},
{"timestamp":"2026-10-12T11:01:00+00:00","home_probability":0.776974},
{"timestamp":"2026-10-12T11:02:00+00:00","home_probability":0.781368},
{"timestamp":"2026-10-12T11:03:00+00:00","home_probability":0.790211},
{"timestamp":"2026-10-12T11:04:00+00:00","home_probability":0.813658},
{"timestamp":"2026-10-12T11:05:00+00:00","home_probability":0.792868},
{"timestamp":"2026-10-12T11:06:00+00:00","home_probability":0.778184},
{"timestamp":"2026-10-12T11:07:00+00:00","home_probability":0.790947},
{"timestamp":"2026-10-12T11:08:00+00:00","home_probability":0.800211},
{"timestamp":"2026-10-12T11:09:00+00:00","home_probability":0.791289},
{"timestamp":"2026-10-12T11:10:00+00:00","home_probability":0.789711},
{"timestamp":"2026-10-12T11:11:00+00:00","home_probability":0.793842},
{"timestamp":"2026-10-12T11:12:00+00:00","home_probability":0.786263},
{"timestamp":"2026-10-12T11:13:00+00:00","home_probability":0.800526},
{"timestamp":"2026-10-12T11:14:00+00:00","home_probability":0.837579},
{"timestamp":"2026-10-12T11:15:00+00:00","home_probability":0.847026},
{"timestamp":"2026-10-12T11:16:00+00:00","home_probability":0.835158},
{"timestamp":"2026-10-12T11:17:00+00:00","home_probability":0.801184},
{"timestamp":"2026-10-12T11:18:00+00:00","home_probability":0.7965},
{"timestamp":"2026-10-12T11:19:00+00:00","home_probability":0.771026},
{"timestamp":"2026-10-12T11:20:00+00:00","home_probability":0.781316},
{"timestamp":"2026-10-12T11:21:00+00:00","home_probability":0.794579},
{"timestamp":"2026-10-12T11:22:00+00:00","home_probability":0.791},
{"timestamp":"2026-10-12T11:23:00+00:00","home_probability":0.791447},
{"timestamp":"2026-10-12T11:24:00+00:00","home_probability":0.785211},
{"timestamp":"2026-10-12T11:25:00+00:00","home_probability":0.772711},
{"timestamp":"2026-10-12T11:26:00+00:00","home_probability":0.760974},
{"timestamp":"2026-10-12T11:27:00+00:00","home_probability":0.763132},
{"timestamp":"2026-10-12T11:28:00+00:00","home_probability":0.783132},
{"timestamp":"2026-10-12T11:29:00+00:00","home_probability":0.760395},
{"timestamp":"2026-10-12T11:30:00+00:00","home_probability":0.768211},
{"timestamp":"2026-10-12T11:31:00+00:00","home_probability":0.767158},
{"timestamp":"2026-10-12T11:32:00+00:00","home_probability":0.792368},
{"timestamp":"2026-10-12T11:33:00+00:00","home_probability":0.822421},
{"timestamp":"2026-10-12T11:34:00+00:00","home_probability":0.821895},
{"timestamp":"2026-10-12T11:35:00+00:00","home_probability":0.820868},
{"timestamp":"2026-10-12T11:36:00+00:00","home_probability":0.786105},
{"timestamp":"2026-10-12T11:37:00+00:00","home_probability":0.757132},
{"timestamp":"2026-10-12T11:38:00+00:00","home_probability":0.760026},
{"timestamp":"2026-10-12T11:39:00+00:00","home_probability":0.756632},
{"timestamp":"2026-10-12T11:40:00+00:00","home_probability":0.773842},
{"timestamp":"2026-10-12T11:41:00+00:00","home_probability":0.776158},
{"timestamp":"2026-10-12T11:42:00+00:00","home_probability":0.746053},
{"timestamp":"2026-10-12T11:43:00+00:00","home_probability":0.726447},
{"timestamp":"2026-10-12T11:44:00+00:00","home_probability":0.688737},
{"timestamp":"2026-10-12T11:45:00+00:00","home_probability":0.613763},
{"timestamp":"2026-10-12T11:46:00+00:00","home_probability":0.518737},
{"timestamp":"2026-10-12T11:47:00+00:00","home_probability":0.5035},
{"timestamp":"2026-10-12T11:48:00+00:00","home_probability":0.478763},
{"timestamp":"2026-10-12T11:49:00+00:00","home_probability":0.502816},
{"timestamp":"2026-10-12T11:50:00+00:00","home_probability":0.5155},
{"timestamp":"2026-10-12T11:51:00+00:00","home_probability":0.553921},
{"timestamp":"2026-10-12T11:52:00+00:00","home_probability":0.545289},
{"timestamp":"2026-10-12T11:53:00+00:00","home_probability":0.596711},
{"timestamp":"2026-10-12T11:54:00+00:00","home_probability":0.535868},
{"timestamp":"2026-10-12T11:55:00+00:00","home_probability":0.465158},
{"timestamp":"2026-10-12T11:56:00+00:00","home_probability":0.486158},
{"timestamp":"2026-10-12T11:57:00+00:00","home_probability":0.479211},
{"timestamp":"2026-10-12T11:58:00+00:00","home_probability":0.508158},
{"timestamp":"2026-10-12T11:59:00+00:00","home_probability":0.509},
{"timestamp":"2026-10-12T12:00:00+00:00","home_probability":0.502053},
{"timestamp":"2026-10-12T12:01:00+00:00","home_probability":0.487263},
{"timestamp":"2026-10-12T12:02:00+00:00","home_probability":0.481184},
{"timestamp":"2026-10-12T12:03:00+00:00","home_probability":0.449737},
{"timestamp":"2026-10-12T12:04:00+00:00","home_probability":0.379947},
{"timestamp":"2026-10-12T12:05:00+00:00","home_probability":0.428026},
{"timestamp":"2026-10-12T12:06:00+00:00","home_probability":0.272237},
{"timestamp":"2026-10-12T12:07:00+00:00","home_probability":0.235316},
{"timestamp":"2026-10-12T12:08:00+00:00","home_probability":0.240605},
{"timestamp":"2026-10-12T12:09:00+00:00","home_probability":0.285816},
{"timestamp":"2026-10-12T12:10:00+00:00","home_probability":0.382},
{"timestamp":"2026-10-12T12:11:00+00:00","home_probability":0.464658},
{"timestamp":"2026-10-12T12:12:00+00:00","home_probability":0.496842},
{"timestamp":"2026-10-12T12:13:00+00:00","home_probability":0.524658},
{"timestamp":"2026-10-12T12:14:00+00:00","home_probability":0.517342},
{"timestamp":"2026-10-12T12:15:00+00:00","home_probability":0.543947},
{"timestamp":"2026-10-12T12:16:00+00:00","home_probability":0.524342},
{"timestamp":"2026-10-12T12:17:00+00:00","home_probability":0.540316},
{"timestamp":"2026-10-12T12:18:00+00:00","home_probability":0.502105},
{"timestamp":"2026-10-12T12:19:00+00:00","home_probability":0.406789},
{"timestamp":"2026-10-12T12:20:00+00:00","home_probability":0.319684},
{"timestamp":"2026-10-12T12:21:00+00:00","home_probability":0.310237},
{"timestamp":"2026-10-12T12:22:00+00:00","home_probability":0.224132},
{"timestamp":"2026-10-12T12:23:00+00:00","home_probability":0.203605},
{"timestamp":"2026-10-12T12:24:00+00:00","home_probability":0.39729},
{"timestamp":"2026-10-12T12:24:06.030278+00:00","home_probability":0.205895}
],
"blend_edge_pinned":true,
"blend_edge_observed_at":"2026-10-12T12:23:57.169564+00:00",
"blend_edge_fold_revision":{"15327807":3649,"15327767":1015},
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{"sportsbook":{"spread":3.5,"home_margin":-3.5,"confidence":1.0,"contracts":[]}},"implied_totals":{"sportsbook":{"total":22.5,"confidence":1.0,"contracts":[]}},"projected_final":{"home_score":9.5,"away_score":13.0,"spread_source":"sportsbook","total_source":"sportsbook"}},
"points":113,
"bookmaker_count":8,
"snapshot_count":473,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##

    static let finalHistory = ##"""
{"event_id":15327291,
"home_team":"Alejandro Davidovich Fokina",
"away_team":"Frances Tiafoe",
"commence_time":"2026-10-11T12:50:00+00:00",
"completed_at":"2026-10-11T15:40:42.437702+00:00",
"status":"completed",
"time_domain":{"start":"2026-10-11T12:50:00+00:00","end":"2026-10-11T16:10:42.437702+00:00","is_live":false,"min_window_seconds":1800},
"history":[
{"timestamp":"2026-10-09T12:00:00+00:00","home_probability":0.4383,"away_probability":0.5617,"over_under":22.5,"projected_home_score":10.5,"projected_away_score":12.0,"bookmaker_count":2,"probability_range":{"min":0.431,"max":0.4455}},
{"timestamp":"2026-10-09T12:01:00+00:00","home_probability":0.436,"away_probability":0.564,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":2,"probability_range":{"min":0.4319,"max":0.4401}},
{"timestamp":"2026-10-11T15:37:00+00:00","home_probability":0.6991,"away_probability":0.3009,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":3,"probability_range":{"min":0.6817,"max":0.7122}},
{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":1.0,"away_probability":0.0,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":0,"probability_range":{"min":1.0,"max":1.0}}
],
"bookmaker_history":{},
"score_history":[],
"espn_history":[],
"win_prob_history":{"polymarket":[
{"timestamp":"2026-10-10T05:20:18.837001+00:00","home_probability":0.505,"away_probability":0.495,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":1.0,"away_probability":0.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}
],"kalshi":[
{"timestamp":"2026-10-10T07:09:37.565755+00:00","home_probability":0.51,"away_probability":0.49,"draw_probability":null,"game_state":null},
{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":1.0,"away_probability":0.0,"draw_probability":null,"game_state":null,"evidence":{"kind":"final"}}
]},
"evidence_contract":{"v":"7878.v1","resolution_s":300},
"win_prob_sources":{"polymarket":{"display_name":"Polymarket","type":"market","color":"#3b82f6","dash_pattern":"8 4","description":"Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.","methodology":"The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.","attribution_url":"https://polymarket.com","attribution_name":"Polymarket","snapshot_count":592},"kalshi":{"display_name":"Kalshi","type":"market","color":"#22c55e","dash_pattern":"8 4","description":"Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.","methodology":"The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.","attribution_url":"https://kalshi.com","attribution_name":"Kalshi","snapshot_count":769}},
"scoring_plays":[],
"moments":[],
"period_markers":[],
"aggregate_line":[
{"timestamp":"2026-10-09T12:00:00+00:00","home_probability":0.4383},
{"timestamp":"2026-10-11T12:40:00+00:00","home_probability":0.465},
{"timestamp":"2026-10-11T12:41:00+00:00","home_probability":0.47},
{"timestamp":"2026-10-11T12:42:00+00:00","home_probability":0.465},
{"timestamp":"2026-10-11T12:43:00+00:00","home_probability":0.465},
{"timestamp":"2026-10-11T12:44:00+00:00","home_probability":0.465},
{"timestamp":"2026-10-11T12:45:00+00:00","home_probability":0.4573},
{"timestamp":"2026-10-11T12:46:00+00:00","home_probability":0.465},
{"timestamp":"2026-10-11T12:47:00+00:00","home_probability":0.4613},
{"timestamp":"2026-10-11T12:48:00+00:00","home_probability":0.455},
{"timestamp":"2026-10-11T12:49:00+00:00","home_probability":0.46},
{"timestamp":"2026-10-11T12:50:00+00:00","home_probability":0.45808},
{"timestamp":"2026-10-11T12:51:00+00:00","home_probability":0.45484},
{"timestamp":"2026-10-11T12:52:00+00:00","home_probability":0.434485},
{"timestamp":"2026-10-11T12:53:00+00:00","home_probability":0.45136},
{"timestamp":"2026-10-11T12:54:00+00:00","home_probability":0.4598},
{"timestamp":"2026-10-11T12:55:00+00:00","home_probability":0.464465},
{"timestamp":"2026-10-11T12:56:00+00:00","home_probability":0.466795},
{"timestamp":"2026-10-11T12:57:00+00:00","home_probability":0.44929},
{"timestamp":"2026-10-11T12:58:00+00:00","home_probability":0.44429},
{"timestamp":"2026-10-11T12:59:00+00:00","home_probability":0.41223},
{"timestamp":"2026-10-11T13:00:00+00:00","home_probability":0.42497},
{"timestamp":"2026-10-11T15:33:00+00:00","home_probability":0.419385},
{"timestamp":"2026-10-11T15:34:00+00:00","home_probability":0.301035},
{"timestamp":"2026-10-11T15:35:00+00:00","home_probability":0.437845},
{"timestamp":"2026-10-11T15:36:00+00:00","home_probability":0.624405},
{"timestamp":"2026-10-11T15:37:00+00:00","home_probability":0.650935},
{"timestamp":"2026-10-11T15:38:00+00:00","home_probability":0.88981},
{"timestamp":"2026-10-11T15:39:00+00:00","home_probability":0.891273},
{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":0.891273},
{"timestamp":"2026-10-11T15:41:00+00:00","home_probability":0.891273},
{"timestamp":"2026-10-11T15:42:00+00:00","home_probability":0.89111},
{"timestamp":"2026-10-11T15:44:00+00:00","home_probability":0.89111},
{"timestamp":"2026-10-11T15:45:00+00:00","home_probability":0.891273},
{"timestamp":"2026-10-11T15:46:00+00:00","home_probability":0.89111},
{"timestamp":"2026-10-11T15:47:00+00:00","home_probability":0.891273},
{"timestamp":"2026-10-11T15:48:00+00:00","home_probability":0.89111},
{"timestamp":"2026-10-11T15:50:00+00:00","home_probability":0.89111},
{"timestamp":"2026-10-11T15:51:00+00:00","home_probability":0.891162},
{"timestamp":"2026-10-11T15:52:00+00:00","home_probability":0.891202},
{"timestamp":"2026-10-11T15:53:00+00:00","home_probability":0.891251},
{"timestamp":"2026-10-11T15:55:00+00:00","home_probability":0.891335},
{"timestamp":"2026-10-11T15:56:00+00:00","home_probability":0.891335},
{"timestamp":"2026-10-11T16:00:00+00:00","home_probability":0.891335},
{"timestamp":"2026-10-11T16:07:00+00:00","home_probability":0.891335},
{"timestamp":"2026-10-11T15:40:00+00:00","home_probability":1.0}
],
"blend_edge_pinned":false,
"blend_edge_observed_at":null,
"blend_edge_fold_revision":null,
"pre_window_omitted":false,
"commence_time_is_kickoff":true,
"pm_spread_data":{"implied_spreads":{},"implied_totals":{},"projected_final":null},
"points":213,
"bookmaker_count":8,
"snapshot_count":860,
"espn_snapshot_count":0,
"on_demand_backfill":null}
"""##
}
