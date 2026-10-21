import XCTest
@testable import Bain_Luck

/// The backend projects one fenced event ledger onto a multi-row page. The
/// reader consumes that whole blend; it never recalculates venue weights.
@MainActor
final class FoldedBlendPreview10090Tests: XCTestCase {
    private let id = 4242
    private let observed = "2026-10-21T20:00:04Z"

    private func wire(seq: Int = 1, epoch: Int = 5, ttl: Int = 1_000,
                      away: Any = 0.2, sport: Any = "soccer_epl") -> [String: Any] {
        ["event_id": id, "p": 0.6, "p_away": away, "sport": sport, "status": "live",
         "display_observed_at": observed,
         "preview": ["kind": "blend", "epoch": epoch, "seq": seq, "base_rev": 20,
                     "ttl_ms": ttl, "folded_version": 1, "origin_event_id": 4243,
                     "base_fold_revision": ["4242": 10, "4243": 20],
                     "pending_entries_version": 2, "pending_entries_authority": "event-ledger-v1"]]
    }

    private func raw(_ value: [String: Any]) throws -> String {
        String(data: try JSONSerialization.data(withJSONObject: value), encoding: .utf8)!
    }

    private func frame(seq: Int = 1, epoch: Int = 5, ttl: Int = 1_000,
                       away: Any = 0.2) throws -> BlendPreviewFrame {
        try XCTUnwrap(BlendPreviewFrame.decode(raw(wire(seq: seq, epoch: epoch, ttl: ttl, away: away))))
    }

    private func detail(revision: [String: Int] = ["4242": 10, "4243": 20],
                        status: String = "live", sport: String = "soccer_epl") throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let payload: [String: Any] = ["id": id, "home_team": "Home", "away_team": "Away",
            "sport": sport, "status": status,
            "current_odds": ["home_probability": 0.5, "away_probability": 0.25],
            "hero_probability": 0.5, "hero_probability_away": 0.25, "hero_probability_source": "blend",
            "blend_fold_revision": revision]
        return try d.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private func reader(seq: Int = 1, away: Any = 0.2) throws -> BlendPreviewReader {
        BlendPreview.readerAfter(.empty, try frame(seq: seq, away: away), eventId: id, now: 100)
    }

    func testFoldedHeadlineChartAndClockUseSameAdmission() throws {
        let r = try reader(), event = try detail()
        let clock = try XCTUnwrap(observed.asDate)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: event, now: 100), 0.6)
        XCTAssertEqual(BlendPreview.overlay(event, r.held, now: 100).currentOdds?.awayProbability, 0.2)
        XCTAssertEqual(BlendPreview.displayedObservedAt(r.held, held: event, now: 100, committed: nil), clock)
        XCTAssertEqual(BlendPreview.chartFrames([], history: nil, state: r.held, held: event, now: 100),
                       [LiveBlendPoint(date: clock, homeProbability: 0.6,
                                       previewAuthority: .init(eventId: id, base: try XCTUnwrap(r.held?.baseFoldRevision)))])
        XCTAssertNil(BlendPreview.displayed(r.held, held: event, now: 101), "expiry is exact")
        XCTAssertEqual(BlendPreview.chartFrames([], history: nil, state: r.held, held: event, now: 101), [])
        XCTAssertNil(BlendPreview.displayedObservedAt(r.held, held: event, now: 101, committed: nil))
    }

    func testDrawAwayIsTheServedValueIncludingNull() throws {
        let event = try detail()
        let shown = BlendPreview.overlay(event, try reader().held, now: 100)
        XCTAssertEqual(shown.heroProbabilityAway, 0.2)
        XCTAssertNotEqual(shown.heroProbabilityAway, 0.4, "not the complement in a draw market")
        let null = BlendPreview.overlay(event, try reader(away: NSNull()).held, now: 100)
        XCTAssertNil(null.heroProbabilityAway)
        XCTAssertNil(null.currentOdds?.awayProbability)
    }

    func testFullMembershipAndEveryRevisionMustMatchAndBeCovered() throws {
        let r = try reader()
        for revision in [["4242": 10], ["4242": 10, "4243": 21], ["4242": 11, "4243": 19],
                         ["4242": 10, "4244": 20], ["4242": 10, "4243": 20, "4244": 0]] {
            XCTAssertNil(BlendPreview.displayed(r.held, held: try detail(revision: revision), now: 100))
        }
        XCTAssertNil(BlendPreview.displayed(r.held, held: try detail(status: "final"), now: 100))
        XCTAssertNil(BlendPreview.displayed(r.held, held: try detail(sport: "basketball_nba"), now: 100))
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ["4242": 9, "4243": 20]), now: 100), 0.6)
    }

    func testUnknownMalformedAndPartialFoldedMetadataNeverFallsBackToSingleton() throws {
        var invalid: [[String: Any]] = []
        for (key, value) in [("folded_version", 2 as Any), ("folded_version", NSNull()),
                             ("origin_event_id", 0), ("origin_event_id", 4244),
                             ("base_rev", 19), ("base_fold_revision", ["4242": 10]),
                             ("base_fold_revision", ["04242": 10, "4243": 20]),
                             ("base_fold_revision", ["4242": 10, "4243": -1])] {
            var w = wire(), p = w["preview"] as! [String: Any]
            p[key] = value; w["preview"] = p; invalid.append(w)
        }
        for key in ["folded_version", "base_fold_revision", "origin_event_id"] {
            var w = wire(), p = w["preview"] as! [String: Any]
            p.removeValue(forKey: key); w["preview"] = p; invalid.append(w)
        }
        for key in ["p_away", "sport"] {
            var w = wire(); w.removeValue(forKey: key); invalid.append(w)
        }
        var badAway = wire(); badAway["p_away"] = 1.1; invalid.append(badAway)
        for w in invalid { XCTAssertNil(BlendPreviewFrame.decode(try raw(w)), "\(w)") }
    }

    func testFloorWithdrawsBeforeQuoteAndCannotBeForgottenByReset() throws {
        let r = try reader()
        let floor = #"{"event_id":4242,"floor":{"4243":21}}"#
        var withdrawn = BlendPreview.readerAfterCommitFloor(r, raw: floor, eventId: id)
        XCTAssertNil(withdrawn.held)
        withdrawn.held = nil // same reset as reconnect/resync
        let replay = BlendPreview.readerAfter(withdrawn, try frame(seq: 2), eventId: id, now: 100.5)
        XCTAssertNil(replay.held)
        XCTAssertEqual(replay.floors?.rows, ["4243": 21])
        let olderFloor = BlendPreview.readerAfterCommitFloor(replay, FoldRevision(["4243": 19]))
        XCTAssertEqual(olderFloor.floors?.rows, ["4243": 21])
    }

    func testMalformedFloorClearsButWrongEventDoesNot() throws {
        let r = try reader()
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, raw: "broken", eventId: id).held)
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, raw: #"{"event_id":4242,"floor":{}}"#, eventId: id).held)
        XCTAssertEqual(BlendPreview.readerAfterCommitFloor(r, raw: #"{"event_id":9,"floor":{"4243":21}}"#, eventId: id), r)
    }

    func testReconnectAndExpiryNeverRenewAReplayedSequence() throws {
        var reset = try reader()
        reset.held = nil
        XCTAssertNil(BlendPreview.readerAfter(reset, try frame(), eventId: id, now: 200).held)
        XCTAssertNil(BlendPreview.readerAfter(reset, try frame(epoch: 4), eventId: id, now: 200).held)
        XCTAssertEqual(BlendPreview.readerAfter(reset, try frame(seq: 2), eventId: id, now: 200).held?.expiresAt, 201)
    }

    func testRevokeMustNameTheOriginAndReplayCannotResurrectIt() throws {
        let r = try reader()
        func revoke(origin: Int) throws -> BlendPreviewFrame {
            try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": NSNull(),
                "preview": ["kind": "revoke", "epoch": 5, "seq": 2, "through_seq": 1,
                            "origin_event_id": origin]])))
        }
        XCTAssertEqual(BlendPreview.readerAfter(r, try revoke(origin: id), eventId: id, now: 100.1), r)
        let withdrawn = BlendPreview.readerAfter(r, try revoke(origin: 4243), eventId: id, now: 100.1)
        XCTAssertNil(withdrawn.held)
        XCTAssertNil(BlendPreview.readerAfter(withdrawn, try frame(), eventId: id, now: 100.2).held)
        XCTAssertEqual(BlendPreview.readerAfter(withdrawn, try frame(seq: 3), eventId: id, now: 100.2).held?.seq, 3)
    }

    func testSingletonContinuesToWorkButCannotMasqueradeAsFolded() throws {
        let f = BlendPreviewFrame(eventId: id, p: 0.7, status: "live", kind: .blend,
                                  epoch: 1, seq: 1, baseRev: 10, ttlMs: 1_000)
        let r = BlendPreview.readerAfter(.empty, f, eventId: id, now: 100)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ["4242": 10]), now: 100), 0.7)
        XCTAssertNil(BlendPreview.displayed(r.held, held: try detail(), now: 100))
        XCTAssertNil(BlendPreview.displayed(try reader().held, held: try detail(revision: ["4242": 10]), now: 100))
    }
    private func pinnedHistory(eventId: Int = 4242, observed: String = "2026-10-21T20:00:00Z",
                               pinned: Bool = true, vector: [String: Int] = ["4242": 10, "4243": 20],
                               realTime: String = "2026-10-21T19:59:00Z",
                               edgeTime: String = "2026-10-21T20:00:10Z") throws -> EventHistoryResponse {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: [
            "event_id": eventId, "home_team": "Home", "away_team": "Away", "status": "live", "history": [],
            "aggregate_line": [["timestamp": realTime, "home_probability": 0.45],
                               ["timestamp": edgeTime, "home_probability": 0.5]],
            "blend_edge_pinned": pinned, "blend_edge_observed_at": observed, "blend_edge_fold_revision": vector]))
    }

    func testOnlyAProvenSyntheticPinCanYieldToTheActualObservation() throws {
        let r = try reader(), event = try detail(), h = try pinnedHistory()
        let frames = BlendPreview.chartFrames([], history: h, state: r.held, held: event, now: 100)
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.date, observed.asDate)
        XCTAssertEqual(h.aggregateLine?.count, 2, "served history was not modified")
        for unsafe in [try pinnedHistory(eventId: 9), try pinnedHistory(observed: "bad"),
                       try pinnedHistory(observed: "2026-10-21T20:00:05Z"), try pinnedHistory(pinned: false),
                       try pinnedHistory(vector: ["4242": 11, "4243": 20]),
                       try pinnedHistory(vector: ["4242": 11, "4243": 20], edgeTime: "2026-10-21T20:00:03Z"),
                       try pinnedHistory(vector: ["4242": 10]), try pinnedHistory(realTime: "bad"),
                       try pinnedHistory(realTime: "2026-10-21T20:00:05Z")] {
            XCTAssertEqual(BlendPreview.chartFrames([], history: unsafe, state: r.held, held: event, now: 100), [])
        }
    }

    func testActualChartReplacesOnlyMatchingPinAndRestoresItWithoutPreview() throws {
        let r = try reader(), event = try detail(), h = try pinnedHistory()
        let served = try XCTUnwrap(h.aggregateLine).map {
            ChartDataPoint(date: $0.timestamp.asDate!, probability: $0.homeProbability, source: "aggregate")
        }
        let venue = ChartDataPoint(date: observed.asDate!, probability: 0.7, source: "polymarket")
        let points = served + [venue]
        let preview = BlendPreview.chartFrames([], history: h, state: r.held, held: event, now: 100)
        let shown = OddsChartView.extendingBlendToLiveEdge(points, with: preview, history: h)
        XCTAssertEqual(shown.filter { $0.source == "aggregate" }.map(\.date),
                       [served[0].date, observed.asDate!])
        XCTAssertEqual(shown.filter { $0.source == "aggregate" }.last?.probability, 0.6)
        XCTAssertEqual(shown.filter { $0.source == "polymarket" }.map(\.id), [venue.id])
        XCTAssertEqual(OddsChartView.extendingBlendToLiveEdge(points, with: [], history: h).map(\.id), points.map(\.id))
        XCTAssertEqual(OddsChartView.extendingBlendToLiveEdge(points, with: preview,
                         history: try pinnedHistory(vector: ["4242": 11, "4243": 20])).map(\.id), points.map(\.id))
        // A newer committed revision wins even when its observation/pin is
        // earlier than the provisional timestamp (independent reviewer case).
        let newerEarlier = try pinnedHistory(vector: ["4242": 11, "4243": 20], edgeTime: "2026-10-21T20:00:03Z")
        let earlierPoints = try XCTUnwrap(newerEarlier.aggregateLine).map {
            ChartDataPoint(date: $0.timestamp.asDate!, probability: $0.homeProbability, source: "aggregate")
        }
        XCTAssertEqual(OddsChartView.extendingBlendToLiveEdge(earlierPoints, with: preview,
                         history: newerEarlier).map(\.id), earlierPoints.map(\.id))
        let mismatch = [served[0], ChartDataPoint(date: served[1].date, probability: 0.51, source: "aggregate")]
        XCTAssertEqual(OddsChartView.extendingBlendToLiveEdge(mismatch, with: preview, history: h).map(\.id), mismatch.map(\.id))
    }

}
