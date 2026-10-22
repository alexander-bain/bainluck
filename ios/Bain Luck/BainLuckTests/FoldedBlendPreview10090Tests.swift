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

    private func origin(_ epoch: Int, _ seq: Int, state: String = "pending", ttl: Int = 1_000) -> [String: Any] {
        var value: [String: Any] = ["epoch": epoch, "seq": seq, "state": state]
        if state == "pending" { value["ttl_ms"] = ttl }
        return value
    }

    private func v2Wire(_ sequence: Int = 1, session: String = "s1", kind: String = "blend",
                        authority: [String: Any]? = nil, ttl: Int = 1_000,
                        base: [String: Int] = ["4242": 10, "4243": 20]) -> [String: Any] {
        ["event_id": id, "p": kind == "blend" ? 0.65 : NSNull(), "p_away": 0.2,
         "sport": "soccer_epl", "status": "live", "display_observed_at": observed,
         "preview": ["kind": kind, "folded_version": 2, "fold_session": session, "fold_seq": sequence,
                     "ttl_ms": kind == "blend" ? ttl : 0,
                     "base_fold_revision": base,
                     "origin_authority": authority ?? ["4242": origin(100, 2), "4243": origin(2, 1)]]]
    }

    private func opened(_ reader: BlendPreviewReader = .empty, session: String = "s1") throws -> BlendPreviewReader {
        BlendPreview.readerOpened(reader, raw: try raw(["event_id": id, "fold_session": session]), eventId: id)
    }

    private func applyV2(_ reader: BlendPreviewReader, _ wire: [String: Any], now: TimeInterval = 100) throws -> BlendPreviewReader {
        BlendPreview.readerAfter(reader, try XCTUnwrap(BlendPreviewFrame.decode(raw(wire))), eventId: id, now: now)
    }

    func testV2IndependentEpochsAndSharedSurfaceAdmission() throws {
        let first = try applyV2(opened(), v2Wire(authority: ["4242": origin(100, 2)]))
        let both = try applyV2(first, v2Wire(2))
        XCTAssertEqual(both.originFences["4243"]?.epoch, 2, "B does not compare with A epoch100")
        XCTAssertEqual(both.originFences["4242"]?.seq, 2)
        let event = try detail()
        XCTAssertEqual(BlendPreview.displayed(both.held, held: event, now: 100), 0.65)
        XCTAssertEqual(BlendPreview.overlay(event, both.held, now: 100).heroProbabilityAway, 0.2)
        XCTAssertEqual(BlendPreview.displayedObservedAt(both.held, held: event, now: 100, committed: nil), observed.asDate)
        XCTAssertEqual(BlendPreview.chartFrames([], history: nil, state: both.held, held: event, now: 100).last?.homeProbability, 0.65)
        XCTAssertNil(BlendPreview.displayed(both.held, held: event, now: 101))
    }

    func testV2CannotLoseSiblingOrAdvanceFencesOnPartialValidation() throws {
        let first = try applyV2(opened(), v2Wire())
        let missing = try applyV2(first, v2Wire(2, authority: ["4243": origin(2, 2)]))
        XCTAssertEqual(missing, first)
        let incomparable = try applyV2(first, v2Wire(2, authority: ["4242": origin(100, 1), "4243": origin(3, 20)]))
        XCTAssertEqual(incomparable, first, "bad A cannot advance B or fold_seq")
        let merged = try applyV2(first, v2Wire(2, authority: ["4242": origin(100, 2), "4243": origin(2, 2)]))
        XCTAssertEqual(merged.foldSeq, 2)
        XCTAssertEqual(merged.originFences["4243"]?.seq, 2)
        XCTAssertEqual(try applyV2(merged, v2Wire(2)), merged, "old fold sequence cannot mutate authority")
    }

    func testV2RetirementRecomposesSiblingAndCannotResurrect() throws {
        let first = try applyV2(opened(), v2Wire())
        for state in ["revoked", "expired", "committed"] {
            let retired = try applyV2(first, v2Wire(2, authority: ["4242": origin(100, 2, state: state), "4243": origin(2, 1)]))
            XCTAssertEqual(retired.held?.p, 0.65, "server recomposition keeps B")
            XCTAssertEqual(retired.originFences["4242"]?.retired, true)
            XCTAssertEqual(try applyV2(retired, v2Wire(3)), retired, "same tuple cannot return")
            let newer = try applyV2(retired, v2Wire(3, authority: ["4242": origin(100, 3), "4243": origin(2, 1)]))
            XCTAssertEqual(newer.originFences["4242"]?.retired, false)
        }
        let withdrawn = try applyV2(first, v2Wire(2, kind: "revoke", authority: [
            "4242": origin(100, 3, state: "revoked"), "4243": origin(2, 2, state: "revoked")]))
        XCTAssertNil(withdrawn.held)
        XCTAssertEqual(withdrawn.foldSeq, 2)
        XCTAssertEqual(try applyV2(withdrawn, v2Wire(3)), withdrawn)
    }

    func testV2SiblingActivityAndReconnectCannotExtendLease() throws {
        let first = try applyV2(opened(), v2Wire())
        let update = try applyV2(first, v2Wire(2, authority: ["4242": origin(100, 2), "4243": origin(2, 2)]), now: 100.7)
        XCTAssertEqual(update.held?.expiresAt, 101)
        XCTAssertEqual(update.originFences["4243"]?.deadline, 101.7)
        let reset = BlendPreview.readerReset(update)
        XCTAssertNil(reset.held)
        XCTAssertNil(reset.foldSession)
        let newSession = try opened(reset, session: "s2")
        let replay = try applyV2(newSession, v2Wire(session: "s2"), now: 100.8)
        XCTAssertEqual(replay, newSession, "B sequence regresses")
        let same = try applyV2(newSession, v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4243": origin(2, 2)]), now: 100.8)
        XCTAssertEqual(same.held?.expiresAt, 101)
        XCTAssertEqual(try applyV2(same, v2Wire(2, session: "s2", authority: ["4242": origin(100, 2), "4243": origin(2, 3)]), now: 101.01), same)
    }

    func testV2NewSessionMayOmitQuietPriorOriginButPreservesItsFence() throws {
        let first = try applyV2(opened(), v2Wire())
        let next = try opened(BlendPreview.readerReset(first), session: "s2")
        let onlyB = try applyV2(next, v2Wire(session: "s2", authority: ["4243": origin(2, 2)]), now: 100.2)
        XCTAssertEqual(onlyB.held?.p, 0.65)
        XCTAssertEqual(onlyB.sessionOrigins, ["4243"])
        XCTAssertEqual(onlyB.originFences["4242"]?.seq, 2)
        let staleA = try applyV2(onlyB, v2Wire(2, session: "s2", authority: ["4242": origin(100, 1), "4243": origin(2, 2)]))
        XCTAssertEqual(staleA, onlyB)
        XCTAssertEqual(try applyV2(onlyB, v2Wire(20, session: "s1")), onlyB)
    }

    func testV2OpenSessionAndDowngradeFences() throws {
        XCTAssertEqual(try applyV2(.empty, v2Wire()), .empty)
        let first = try applyV2(opened(), v2Wire())
        XCTAssertEqual(try opened(first, session: "attacker"), first, "unsolicited open cannot swap active session")
        let badOpen = BlendPreview.readerOpened(.empty, raw: #"{"event_id":999,"fold_session":"s1"}"#, eventId: id)
        XCTAssertEqual(badOpen, .empty)
        let reset = BlendPreview.readerReset(first)
        XCTAssertEqual(BlendPreview.readerAfter(reset, try frame(epoch: 999), eventId: id, now: 100), reset)
        let floor = BlendPreview.readerAfterCommitFloor(first, FoldRevision(["4243": 21]))
        XCTAssertNil(floor.held)
        XCTAssertEqual(try applyV2(floor, v2Wire(2)), floor, "uncovered floor cannot advance fences")
    }

    func testV2MalformedAuthorityNeverDecodesOrFallsBack() throws {
        var invalid: [[String: Any]] = []
        for (key, value) in [("folded_version", 3 as Any), ("fold_session", ""), ("fold_seq", -1),
                             ("origin_authority", [:]), ("origin_authority", ["4244": origin(1, 1)]),
                             ("origin_authority", ["04242": origin(1, 1)]),
                             ("origin_authority", ["4242": origin(1, 1, state: "mystery")]),
                             ("origin_authority", ["4242": origin(1, 1, ttl: 0)]),
                             ("origin_authority", ["4242": ["epoch": true, "seq": 1, "state": "pending", "ttl_ms": 1_000]]),
                             ("origin_authority", ["4242": ["epoch": 1, "seq": 1, "state": "revoked", "ttl_ms": NSNull()]])] {
            var w = v2Wire(), meta = w["preview"] as! [String: Any]
            meta[key] = value; w["preview"] = meta; invalid.append(w)
        }
        for key in ["folded_version", "fold_session", "fold_seq", "base_fold_revision", "origin_authority"] {
            var w = v2Wire(), meta = w["preview"] as! [String: Any]
            meta.removeValue(forKey: key); w["preview"] = meta; invalid.append(w)
        }
        var mixed = wire(), mixedMeta = mixed["preview"] as! [String: Any]
        mixedMeta["fold_session"] = "s1"; mixed["preview"] = mixedMeta; invalid.append(mixed)
        invalid.append(v2Wire(ttl: 2_000))
        for status in [NSNull(), "final", "unknown"] as [Any] {
            var w = v2Wire(); w["status"] = status; invalid.append(w)
        }
        var invalidRevoke = v2Wire(kind: "revoke"); invalidRevoke["p"] = 0.6
        invalid.append(invalidRevoke) // withdrawal cannot carry a probability
        for value in invalid { XCTAssertNil(BlendPreviewFrame.decode(try raw(value)), "\(value)") }
        _ = try XCTUnwrap(BlendPreviewFrame.decode(try raw(v2Wire()))) // no scalar epoch/seq
    }

    func testV2ColdBaseWithdrawalPreservesSiblingDeadline() throws {
        let first = try applyV2(opened(), v2Wire())
        var cold = v2Wire(2, kind: "revoke", authority: ["4242": origin(100, 2, state: "committed"), "4243": origin(2, 1)])
        cold.removeValue(forKey: "sport"); cold.removeValue(forKey: "p_away")
        let withdrawn = try applyV2(first, cold, now: 100.4)
        XCTAssertNil(withdrawn.held)
        XCTAssertEqual(withdrawn.originFences["4243"]?.deadline, 101)
        let warm = try applyV2(withdrawn, v2Wire(3, authority: ["4242": origin(100, 2, state: "committed"), "4243": origin(2, 1)]), now: 100.6)
        XCTAssertEqual(warm.held?.expiresAt, 101)
        XCTAssertEqual(warm.held?.p, 0.65)
    }

    func testV2UpgradeRetainsPriorV1OriginFence() throws {
        let prior = try opened(reader())
        let stale = try applyV2(prior, v2Wire(authority: ["4243": origin(4, 999)]))
        XCTAssertEqual(stale, prior)
        let current = try applyV2(prior, v2Wire(authority: ["4243": origin(5, 1)]), now: 100.8)
        XCTAssertEqual(current.held?.expiresAt, 101)
        let reset = try opened(BlendPreview.readerReset(prior), session: "s2")
        XCTAssertEqual(try applyV2(reset, v2Wire(session: "s2", authority: ["4243": origin(5, 1)])), reset)
    }

    /// The membership 1/2 -> 1/3 stall web reproduced, on Native: with only
    /// reset/reconnect as a boundary, the old fold's member set, fences and
    /// floors refuse every snapshot of the new fold for good. The authoritative
    /// membership boundary prunes the removed member and its floor, keeps the
    /// survivor's identity and deadline, withdraws the display, drops the
    /// session, admits the new fold and refuses old-session and old-membership
    /// packets.
    func testV2AuthoritativeMembershipChangeAdmitsTheNewFoldAndRefusesTheOld() throws {
        let old = BlendPreview.readerAfterMembership(try opened(), members: ["4242", "4243"])
        var both = try applyV2(old, v2Wire())
        both = BlendPreview.readerAfterCommitFloor(both, FoldRevision(["4242": 10, "4243": 20]))
        XCTAssertEqual(both.held?.p, 0.65)
        XCTAssertEqual(both.authorityMembers, ["4242", "4243"])
        let newFold = v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4244": origin(7, 1)],
                             base: ["4242": 11, "4244": 30])

        // The reproduced stall: reset (disconnect) and a new session are not a
        // membership boundary; each retained guard alone refuses the new fold.
        let stalled = try opened(BlendPreview.readerReset(both), session: "s2")
        XCTAssertEqual(try applyV2(stalled, newFold, now: 100.3), stalled, "members + fences + floors")
        var onlyMembers = stalled; onlyMembers.originFences = [:]; onlyMembers.floors = nil
        XCTAssertEqual(try applyV2(onlyMembers, newFold, now: 100.3), onlyMembers, "old member set alone")
        var onlyFences = stalled; onlyFences.foldMembers = nil; onlyFences.floors = nil
        XCTAssertEqual(try applyV2(onlyFences, newFold, now: 100.3), onlyFences, "old fences alone (3 origins)")
        var onlyFloors = stalled; onlyFloors.foldMembers = nil; onlyFloors.originFences = [:]
        XCTAssertEqual(try applyV2(onlyFloors, newFold, now: 100.3), onlyFloors, "old floor naming 4243 alone")

        // The authoritative detail now folds 4242 with 4244 instead.
        let changed = BlendPreview.readerAfterMembership(both, members: ["4242", "4244"])
        XCTAssertNil(changed.held, "the old fold's preview is withdrawn")
        XCTAssertNil(changed.foldSession, "the session is dropped so the stream reopens")
        XCTAssertEqual(changed.foldSeq, -1)
        XCTAssertEqual(changed.sessionOrigins, [])
        XCTAssertEqual(changed.foldMembers, ["4242", "4244"])
        XCTAssertEqual(changed.authorityMembers, ["4242", "4244"])
        XCTAssertEqual(Set(changed.originFences.keys), ["4242"], "the removed member loses its fence")
        XCTAssertEqual(changed.originFences["4242"], both.originFences["4242"], "the survivor keeps identity and deadline")
        XCTAssertEqual(changed.floors?.rows, ["4242": 10], "and only the survivor's floor remains")
        XCTAssertEqual(BlendPreview.readerAfterMembership(changed, members: ["4242", "4244"]), changed,
                       "the same membership again records nothing")
        XCTAssertEqual(BlendPreview.readerAfterMembership(changed, members: []), changed, "no membership, no claim")

        // Session two on the new fold is admitted; the survivor's unchanged
        // tuple keeps its first-seen deadline across the change.
        let reopened = try opened(changed, session: "s2")
        let shown = try applyV2(reopened, newFold, now: 100.3)
        XCTAssertEqual(shown.held?.p, 0.65)
        XCTAssertEqual(shown.held?.baseFoldRevision?.rows, ["4242": 11, "4244": 30])
        XCTAssertEqual(BlendPreview.displayed(shown.held, held: try detail(revision: ["4242": 11, "4244": 30]), now: 100.3), 0.65)
        XCTAssertEqual(shown.held?.expiresAt, 101, "A's (100,2) lease is not renewed by the new fold")
        XCTAssertEqual(shown.originFences["4244"]?.epoch, 7)
        XCTAssertEqual(shown.originFences["4244"]?.deadline, 101.3)
        XCTAssertEqual(shown.sessionOrigins, ["4242", "4244"])
        XCTAssertEqual(try applyV2(shown, v2Wire(2, session: "s2", authority: ["4242": origin(100, 1), "4244": origin(7, 2)],
                                        base: ["4242": 11, "4244": 30]), now: 100.4), shown, "an older A tuple stays fenced")

        // Old-fold packets: the old session, and the removed member's membership.
        XCTAssertEqual(try applyV2(shown, v2Wire(2, session: "s1", authority: ["4242": origin(100, 3), "4244": origin(7, 2)],
                                        base: ["4242": 11, "4244": 30]), now: 100.4), shown, "old session")
        XCTAssertEqual(try applyV2(shown, v2Wire(2, session: "s2"), now: 100.4), shown, "old membership 4242/4243")
        XCTAssertEqual(try applyV2(shown, v2Wire(2, session: "s2", authority: ["4242": origin(100, 3), "4243": origin(2, 2)],
                                        base: ["4242": 11, "4243": 21]), now: 100.4), shown, "removed member cannot return")

        // Ordinary disconnect/resync after the change: fences and deadlines stay.
        var resync = shown; resync.held = nil
        XCTAssertEqual(try applyV2(resync, v2Wire(2, session: "s2", authority: ["4242": origin(100, 2), "4244": origin(7, 1)],
                                        base: ["4242": 11, "4244": 30]), now: 100.5).held?.expiresAt, 101)
        let reconnected = try opened(BlendPreview.readerReset(shown), session: "s3")
        XCTAssertEqual(reconnected.originFences, shown.originFences)
        XCTAssertEqual(reconnected.foldMembers, ["4242", "4244"])
        XCTAssertEqual(try applyV2(reconnected, v2Wire(session: "s3", authority: ["4242": origin(100, 2), "4244": origin(7, 1)],
                                        base: ["4242": 11, "4244": 30]), now: 100.6).held?.expiresAt, 101)
    }

    /// A singleton visit that becomes a fold carries its own row's identity and
    /// deadline into the fold's v2 authority. On the v1 folded path, a floor
    /// naming the removed row stalls every new-fold frame until the boundary
    /// prunes it (the ab5 reader has no such boundary).
    func testMembershipChangeCarriesTheSingletonFenceAndPrunesLegacyFloors() throws {
        let single = BlendPreview.readerAfter(
            BlendPreview.readerAfterMembership(.empty, members: ["4242"]),
            BlendPreviewFrame(eventId: id, p: 0.7, status: "live", kind: .blend, epoch: 100, seq: 2, baseRev: 10, ttlMs: 1_000),
            eventId: id, now: 100)
        XCTAssertEqual(BlendPreview.displayed(single.held, held: try detail(revision: ["4242": 10]), now: 100), 0.7)
        let folded = BlendPreview.readerAfterMembership(single, members: ["4242", "4244"])
        XCTAssertNil(folded.held)
        XCTAssertEqual(folded.originFences["4242"],
                       BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: false, deadline: 101))
        let session = try opened(folded, session: "s2")
        let newFold = v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4244": origin(7, 1)],
                             base: ["4242": 10, "4244": 30])
        XCTAssertEqual(try applyV2(session, newFold, now: 100.5).held?.expiresAt, 101,
                       "the singleton's (100,2) lease does not renew in the fold")
        XCTAssertEqual(try applyV2(session, v2Wire(session: "s2", authority: ["4242": origin(100, 1), "4244": origin(7, 1)],
                                          base: ["4242": 10, "4244": 30]), now: 100.5), session, "an older own tuple is fenced")
        XCTAssertEqual(try applyV2(session, newFold, now: 101), session, "the expired tuple stays expired")

        var v1 = BlendPreview.readerAfterMembership(try reader(), members: ["4242", "4243"])
        v1 = BlendPreview.readerAfterCommitFloor(v1, FoldRevision(["4243": 21]))
        XCTAssertNil(v1.held)
        var w = wire(seq: 2), meta = w["preview"] as! [String: Any]
        meta["origin_event_id"] = 4244; meta["base_rev"] = 30; meta["base_fold_revision"] = ["4242": 10, "4244": 30]
        w["preview"] = meta
        let v1New = try XCTUnwrap(BlendPreviewFrame.decode(raw(w)))
        XCTAssertNil(BlendPreview.readerAfter(v1, v1New, eventId: id, now: 100.2).held, "the 4243 floor holds the new fold out")
        let pruned = BlendPreview.readerAfterMembership(v1, members: ["4242", "4244"])
        XCTAssertNil(pruned.floors)
        XCTAssertNil(pruned.foldedSequence, "the removed origin's v1 order is dropped")
        XCTAssertEqual(pruned.epoch, -1, "with the scalar epoch that was its domain")
        let admitted = BlendPreview.readerAfter(pruned, v1New, eventId: id, now: 100.2)
        XCTAssertEqual(admitted.held?.p, 0.6)
        XCTAssertEqual(BlendPreview.displayed(admitted.held, held: try detail(revision: ["4242": 10, "4244": 30]), now: 100.2), 0.6)
        XCTAssertEqual(BlendPreview.readerAfter(pruned, try frame(seq: 3), eventId: id, now: 100.2), pruned,
                       "the old fold's v1 frame (4242/4243) is refused outright")
    }

    /// Review blocker 1 (64a095c4): on the v1 path the scalar epoch is the
    /// origin's own domain. A removed origin's epoch (900) used to keep fencing
    /// the replacement origin's independent epoch (12) after the boundary; the
    /// boundary now takes the removed origin's epoch with its order, and keeps
    /// it when the order's origin survives.
    func testTheRemovedOriginsScalarEpochLeavesWithItAndTheSurvivorsStays() throws {
        func folded(origin: Int, epoch: Int, seq: Int, baseRev: Int, base: [String: Int]) throws -> BlendPreviewFrame {
            var w = wire(seq: seq, epoch: epoch), meta = w["preview"] as! [String: Any]
            meta["origin_event_id"] = origin; meta["base_rev"] = baseRev; meta["base_fold_revision"] = base
            w["preview"] = meta
            return try XCTUnwrap(BlendPreviewFrame.decode(raw(w)))
        }
        let old = BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"])
        let fold2 = BlendPreview.readerAfter(
            old, try folded(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: ["4242": 10, "4243": 20]), eventId: id, now: 100)
        XCTAssertEqual(fold2.epoch, 900)
        XCTAssertEqual(fold2.held?.p, 0.6)
        let origin3 = try folded(origin: 4244, epoch: 12, seq: 81, baseRev: 30, base: ["4242": 10, "4244": 30])
        let reset = BlendPreview.readerReset(fold2)
        XCTAssertEqual(BlendPreview.readerAfter(reset, origin3, eventId: id, now: 100.2), reset,
                       "reset is not a boundary: the removed origin's epoch 900 still fences origin 4244's epoch 12")
        let pruned = BlendPreview.readerAfterMembership(fold2, members: ["4242", "4244"])
        XCTAssertEqual(pruned.epoch, -1)
        XCTAssertNil(pruned.foldedSequence)
        let admitted = BlendPreview.readerAfter(pruned, origin3, eventId: id, now: 100.2)
        XCTAssertEqual(admitted.epoch, 12, "the replacement origin's own epoch is the fence now")
        XCTAssertEqual(admitted.foldedSequence, BlendPreviewReader.FoldedSequence(epoch: 12, seq: 81, originEventId: 4244))
        XCTAssertEqual(BlendPreview.displayed(admitted.held, held: try detail(revision: ["4242": 10, "4244": 30]), now: 100.2), 0.6)
        XCTAssertEqual(BlendPreview.readerAfter(
            admitted, try folded(origin: 4244, epoch: 12, seq: 80, baseRev: 30, base: ["4242": 10, "4244": 30]),
            eventId: id, now: 100.3), admitted, "and it orders against itself")
        XCTAssertEqual(BlendPreview.readerAfter(
            admitted, try folded(origin: 4244, epoch: 12, seq: 82, baseRev: 30, base: ["4242": 10, "4244": 30]),
            eventId: id, now: 100.3).held?.seq, 82)

        // The order's origin survives the change: its epoch is still the fence.
        let own = BlendPreview.readerAfter(
            old, try folded(origin: 4242, epoch: 900, seq: 2, baseRev: 10, base: ["4242": 10, "4243": 20]), eventId: id, now: 100)
        let kept = BlendPreview.readerAfterMembership(own, members: ["4242", "4244"])
        XCTAssertEqual(kept.epoch, 900)
        XCTAssertEqual(kept.foldedSequence, BlendPreviewReader.FoldedSequence(epoch: 900, seq: 2, originEventId: 4242))
        XCTAssertEqual(BlendPreview.readerAfter(
            kept, try folded(origin: 4242, epoch: 12, seq: 81, baseRev: 10, base: ["4242": 10, "4244": 30]),
            eventId: id, now: 100.2), kept, "an older epoch of the surviving origin stays fenced")
    }

    /// Review blocker 2 (64a095c4): the page row's singleton authority is
    /// recorded at acceptance, not read off the display, so a disconnect
    /// before the membership change cannot forget it. The legacy singleton
    /// display rules are unchanged; the record only moves forward, keeps a
    /// same tuple's first-seen deadline and its retirement, and fences the
    /// fold the row later joins: older identity refused, same identity capped
    /// and then expired, revoked identity never pending again.
    func testSingletonAuthorityOutlivesTheDisplayAndFencesTheFoldItJoins() throws {
        func single(_ p: Double, epoch: Int, seq: Int) -> BlendPreviewFrame {
            BlendPreviewFrame(eventId: id, p: p, status: "live", kind: .blend, epoch: epoch, seq: seq, baseRev: 10, ttlMs: 1_000)
        }
        let bound = BlendPreview.readerAfterMembership(.empty, members: ["4242"])
        let accepted = BlendPreview.readerAfter(bound, single(0.7, epoch: 100, seq: 2), eventId: id, now: 100)
        XCTAssertEqual(accepted.originFences["4242"],
                       BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: false, deadline: 101))
        XCTAssertEqual(BlendPreview.displayed(accepted.held, held: try detail(revision: ["4242": 10]), now: 100), 0.7)
        let reset = BlendPreview.readerReset(accepted)
        XCTAssertNil(reset.held)
        XCTAssertEqual(reset.originFences["4242"]?.seq, 2, "the record outlives the display")
        let replay = BlendPreview.readerAfter(reset, single(0.69, epoch: 100, seq: 1), eventId: id, now: 100.2)
        XCTAssertEqual(replay.held?.seq, 1, "the legacy singleton display rules are unchanged")
        XCTAssertEqual(replay.originFences["4242"]?.seq, 2, "but the recorded identity does not move back")
        XCTAssertEqual(BlendPreview.readerAfter(reset, single(0.7, epoch: 100, seq: 2), eventId: id, now: 100.5)
                           .originFences["4242"]?.deadline, 101, "a same tuple keeps its first-seen deadline")
        XCTAssertEqual(BlendPreview.readerAfter(reset, single(0.71, epoch: 101, seq: 1), eventId: id, now: 100.5)
                           .originFences["4242"], BlendPreviewReader.OriginFence(epoch: 101, seq: 1, retired: false, deadline: 101.5))

        // Disconnected, then the authoritative detail folds 4242 with 4244.
        let folded = try opened(BlendPreview.readerAfterMembership(reset, members: ["4242", "4244"]), session: "s2")
        XCTAssertEqual(folded.originFences["4242"],
                       BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: false, deadline: 101))
        let base = ["4242": 10, "4244": 30]
        let older = v2Wire(session: "s2", authority: ["4242": origin(100, 1), "4244": origin(7, 1)], base: base)
        XCTAssertEqual(try applyV2(folded, older, now: 100.5), folded, "an older own tuple cannot enter the fold")
        let same = v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4244": origin(7, 1)], base: base)
        XCTAssertEqual(try applyV2(folded, same, now: 100.5).held?.expiresAt, 101, "the same tuple keeps its first-seen deadline")
        XCTAssertEqual(try applyV2(folded, same, now: 101), folded, "and stays expired past it")
        let newer = v2Wire(session: "s2", authority: ["4242": origin(100, 3), "4244": origin(7, 1)], base: base)
        XCTAssertEqual(try applyV2(folded, newer, now: 100.5).held?.expiresAt, 101.5)

        // A revoked singleton identity cannot become pending again in the fold.
        let revoked = BlendPreview.readerAfter(
            accepted, BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke, epoch: 100, seq: 3, throughSeq: 2),
            eventId: id, now: 100.3)
        XCTAssertNil(revoked.held)
        XCTAssertEqual(revoked.originFences["4242"],
                       BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: true, deadline: 101))
        let revokedFold = try opened(
            BlendPreview.readerAfterMembership(BlendPreview.readerReset(revoked), members: ["4242", "4244"]), session: "s2")
        XCTAssertEqual(try applyV2(revokedFold, same, now: 100.5), revokedFold, "the revoked tuple cannot return as pending")
        XCTAssertEqual(try applyV2(revokedFold, newer, now: 100.5).held?.p, 0.65, "a newer own tuple can")
        // A revoke of older sequences only does not retire the recorded identity.
        let partial = BlendPreview.readerAfter(
            accepted, BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke, epoch: 100, seq: 3, throughSeq: 1),
            eventId: id, now: 100.3)
        XCTAssertEqual(partial.held?.seq, 2)
        XCTAssertEqual(partial.originFences["4242"]?.retired, false)
    }

    /// Review qualification (64a095c4): a cached detail can flap the
    /// membership back for up to a cache window. A row the page stopped folding
    /// leaves bounded evidence behind, and gets it back when it returns, so the
    /// flap cannot resurrect its identity, renew its lease or admit a base its
    /// commit floor had already refused.
    func testARowThatReturnsAfterAMembershipFlapGetsItsEvidenceBack() throws {
        var both = try applyV2(BlendPreview.readerAfterMembership(try opened(), members: ["4242", "4243"]), v2Wire())
        both = BlendPreview.readerAfterCommitFloor(both, FoldRevision(["4242": 10, "4243": 20]))
        let away = BlendPreview.readerAfterMembership(both, members: ["4242", "4244"])
        XCTAssertEqual(away.retiredMembers,
                       [BlendPreviewReader.RetiredMember(row: "4243", fence: both.originFences["4243"], floor: 20)])
        XCTAssertNil(away.originFences["4243"])
        XCTAssertEqual(away.floors?.rows, ["4242": 10])
        XCTAssertEqual(BlendPreview.readerReset(away).retiredMembers, away.retiredMembers, "a reset keeps the evidence")

        // The flap back: 4243's fence and floor return with it; nothing is renewed.
        let back = try opened(BlendPreview.readerAfterMembership(away, members: ["4242", "4243"]), session: "s2")
        XCTAssertEqual(back.retiredMembers, [])
        XCTAssertEqual(back.originFences["4243"], both.originFences["4243"])
        XCTAssertEqual(back.floors?.rows, ["4242": 10, "4243": 20])
        XCTAssertEqual(try applyV2(back, v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4243": origin(2, 0)]), now: 100.4),
                       back, "an older 4243 tuple is still fenced")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "s2", base: ["4242": 10, "4243": 19]), now: 100.4),
                       back, "an uncovered 4243 base is still refused")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "s2"), now: 100.4).held?.expiresAt, 101,
                       "the same tuples keep their first-seen deadlines")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4243": origin(2, 2)]), now: 100.4)
                           .held?.expiresAt, 101)

        // The evidence is never evicted (the independent review of b9c8a143
        // reproduced 4243 forgotten after five removed origins under the old
        // oldest-out bound); capacity saturates the reader instead —
        // `testRetiredEvidenceIsNeverEvictedAndCapacityRefusesInsteadOfForgetting`.
        var churn = back
        for row in ["4245", "4246", "4247", "4248", "4249"] {
            churn = BlendPreview.readerAfterMembership(churn, members: ["4242", row])
            churn = try applyV2(try opened(churn, session: "s-\(row)"),
                                v2Wire(session: "s-\(row)", authority: ["4242": origin(100, 2), row: origin(1, 1)],
                                       base: ["4242": 10, row: 5]), now: 100.4)
            XCTAssertEqual(churn.held?.p, 0.65, row)
        }
        XCTAssertEqual(churn.retiredMembers.map(\.row), ["4243", "4245", "4246", "4247", "4248"],
                       "every row that left, oldest first — nothing aged out")
        XCTAssertEqual(churn.evidenceSaturated, false)
    }

    private func foldedFrame(origin: Int, epoch: Int, seq: Int, baseRev: Int, base: [String: Int]) throws -> BlendPreviewFrame {
        var w = wire(seq: seq, epoch: epoch), meta = w["preview"] as! [String: Any]
        meta["origin_event_id"] = origin; meta["base_rev"] = baseRev; meta["base_fold_revision"] = base
        w["preview"] = meta
        return try XCTUnwrap(BlendPreviewFrame.decode(raw(w)))
    }

    private func singletonFrame(_ p: Double, epoch: Int, seq: Int, baseRev: Int = 10) -> BlendPreviewFrame {
        BlendPreviewFrame(eventId: id, p: p, status: "live", kind: .blend, epoch: epoch, seq: seq, baseRev: baseRev, ttlMs: 1_000)
    }

    /// Independent review of b9c8a143 (remaining blocker): after five removed
    /// origins the oldest-out bound had forgotten 4243's fence and floor, and a
    /// NEW matching session admitted its older identity (2,1) on base 19 — below
    /// the accepted (2,2) and the floor 20 — with a fresh deadline. The exact
    /// retained sequence, on the repaired reader: nothing is forgotten, so the
    /// return is fenced; and past capacity the reader saturates — a COVERAGE
    /// LIMIT, not continuity: it admits nothing more and still forgets nothing.
    func testRetiredEvidenceIsNeverEvictedAndCapacityRefusesInsteadOfForgetting() throws {
        var current = try applyV2(BlendPreview.readerAfterMembership(try opened(), members: ["4242", "4243"]),
                                  v2Wire(authority: ["4243": origin(2, 2)]))
        current = BlendPreview.readerAfterCommitFloor(current, FoldRevision(["4242": 10, "4243": 20]))
        XCTAssertEqual(current.held?.expiresAt, 101)
        let fence4243 = try XCTUnwrap(current.originFences["4243"])
        let churn = ["4245", "4246", "4247", "4248", "4249"]
        for row in churn {
            current = BlendPreview.readerAfterMembership(current, members: ["4242", row])
            current = try applyV2(try opened(current, session: "s-\(row)"),
                                  v2Wire(session: "s-\(row)", authority: [row: origin(1, 1)], base: ["4242": 10, row: 5]), now: 100.4)
            XCTAssertEqual(current.held?.p, 0.65, row)
        }
        XCTAssertEqual(current.retiredMembers.map(\.row), ["4243", "4245", "4246", "4247", "4248"], "nothing aged out")
        XCTAssertEqual(current.evidenceSaturated, false)

        // The review's steps 3-5: 4243 returns in a new matching session.
        let back = try opened(BlendPreview.readerAfterMembership(current, members: ["4242", "4243"]), session: "return")
        XCTAssertEqual(back.originFences["4243"], fence4243, "its fence is back")
        XCTAssertEqual(back.floors?.rows["4243"], 20, "and its floor")
        let base19: [String: Int] = ["4242": 10, "4243": 19]
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 1)], base: base19), now: 101.2), back,
                       "(2,1) below the accepted (2,2), base 19 below floor 20: refused, no new deadline")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 1)]), now: 101.2), back,
                       "the older identity alone is refused")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 2)], base: base19), now: 101.2), back,
                       "the uncovered base alone is refused")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 2)]), now: 101.2), back,
                       "the same tuple is past its first-seen deadline")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 2)]), now: 100.9).held?.expiresAt, 101,
                       "before that deadline it keeps it")
        XCTAssertEqual(try applyV2(back, v2Wire(session: "return", authority: ["4243": origin(2, 3)]), now: 101.2).held?.expiresAt, 102.2,
                       "a newer 4243 tuple resumes the fold")

        // Capacity. Retiring one more distinct row than `maxRetiredMembers`
        // saturates: the row that would have been forgotten is kept, and the
        // visit admits nothing more — not the new fold, not a returning row
        // with a newer tuple, not a legacy singleton — until navigation.
        var full = back
        for row in ["4250", "4251", "4252"] {
            full = BlendPreview.readerAfterMembership(full, members: ["4242", row])
            full = try applyV2(try opened(full, session: "s-\(row)"),
                               v2Wire(session: "s-\(row)", authority: [row: origin(1, 1)], base: ["4242": 10, row: 5]), now: 100.4)
            XCTAssertEqual(full.held?.p, 0.65, row)
        }
        XCTAssertEqual(full.retiredMembers.count, BlendPreviewReader.maxRetiredMembers)
        XCTAssertEqual(full.evidenceSaturated, false, "at capacity is not past it")
        let saturated = BlendPreview.readerAfterMembership(full, members: ["4242", "4253"])
        XCTAssertEqual(saturated.evidenceSaturated, true)
        XCTAssertEqual(saturated.retiredMembers.count, BlendPreviewReader.maxRetiredMembers + 1, "kept, not forgotten")
        XCTAssertEqual(Set(saturated.retiredMembers.map(\.row)),
                       ["4243", "4245", "4246", "4247", "4248", "4249", "4250", "4251", "4252"])
        XCTAssertNil(saturated.held)
        XCTAssertNil(saturated.foldSession, "the old fold's session still goes")
        let refused = try applyV2(try opened(saturated, session: "s-4253"),
                                  v2Wire(session: "s-4253", authority: ["4253": origin(1, 1)], base: ["4242": 10, "4253": 5]), now: 100.4)
        XCTAssertNil(refused.held, "coverage limit: the new fold is not admitted")
        XCTAssertNil(refused.originFences["4253"], "and acquires no authority")
        let returning = try opened(BlendPreview.readerAfterMembership(saturated, members: ["4242", "4243"]), session: "s-again")
        XCTAssertEqual(returning.evidenceSaturated, true)
        XCTAssertEqual(returning.retiredMembers, saturated.retiredMembers, "no evidence moves any more")
        XCTAssertNil(try applyV2(returning, v2Wire(session: "s-again", authority: ["4243": origin(2, 9)]), now: 100.4).held,
                     "nor is a returning row admitted, however new its tuple")
        XCTAssertEqual(BlendPreview.readerReset(saturated).evidenceSaturated, true, "reset keeps the limit")
        XCTAssertEqual(BlendPreview.readerAfter(saturated, singletonFrame(0.7, epoch: 1, seq: 1), eventId: id, now: 100.4), saturated,
                       "the legacy path is closed too")
    }

    /// Remaining blocker 2: a fold that folds down to the page row alone must
    /// resume that row's singleton frames — refused for good on b9c8a143 after
    /// v2 (`enteredV2`) or under a retained v1 order — without protocol
    /// downgrade on a fold, older/equal identity renewal, removed-origin
    /// admission or loss of the row's recorded authority. The never-folded
    /// singleton visit keeps its legacy display rules (the predecessor test).
    func testAFoldDownToThePageRowResumesItsSingletonUnderItsOwnFence() throws {
        let fold = BlendPreview.readerAfterCommitFloor(
            try applyV2(BlendPreview.readerAfterMembership(try opened(), members: ["4242", "4243"]), v2Wire()),
            FoldRevision(["4242": 10, "4243": 20]))
        XCTAssertEqual(fold.held?.p, 0.65)
        let alone = BlendPreview.readerAfterMembership(fold, members: ["4242"])
        XCTAssertNil(alone.held)
        XCTAssertNil(alone.foldSession)
        XCTAssertEqual(alone.foldMembers, ["4242"])
        XCTAssertEqual(alone.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: false, deadline: 101))
        XCTAssertEqual(alone.retiredMembers.map(\.row), ["4243"])
        XCTAssertEqual(alone.floors?.rows, ["4242": 10])
        let page = try detail(revision: ["4242": 10])
        XCTAssertEqual(BlendPreview.readerAfter(alone, singletonFrame(0.69, epoch: 100, seq: 1), eventId: id, now: 100.5), alone,
                       "an older own tuple is refused")
        let same = BlendPreview.readerAfter(alone, singletonFrame(0.7, epoch: 100, seq: 2), eventId: id, now: 100.5)
        XCTAssertEqual(same.held?.expiresAt, 101, "the same tuple keeps its first-seen deadline")
        XCTAssertEqual(BlendPreview.displayed(same.held, held: page, now: 100.5), 0.7, "and the page shows it")
        XCTAssertEqual(BlendPreview.readerAfter(alone, singletonFrame(0.7, epoch: 100, seq: 2), eventId: id, now: 101), alone,
                       "and stays expired past it")
        let newer = BlendPreview.readerAfter(alone, singletonFrame(0.71, epoch: 100, seq: 3), eventId: id, now: 100.5)
        XCTAssertEqual(newer.held?.expiresAt, 101.5)
        XCTAssertEqual(BlendPreview.displayed(newer.held, held: page, now: 100.5), 0.71)
        XCTAssertEqual(newer.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 100, seq: 3, retired: false, deadline: 101.5),
                       "source authority keeps being recorded")
        XCTAssertNil(BlendPreview.readerAfter(alone, singletonFrame(0.7, epoch: 100, seq: 3, baseRev: 9), eventId: id, now: 100.5).held,
                     "a singleton composed below the fold's commit floor is withdrawn")
        // Removed-origin and old-protocol frames have no say.
        XCTAssertEqual(BlendPreview.readerAfter(alone, try frame(seq: 9, epoch: 900), eventId: id, now: 100.5), alone,
                       "the old fold's v1 frame")
        let bareRevoke = try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": NSNull(),
            "preview": ["kind": "revoke", "epoch": 900, "seq": 2, "through_seq": 1, "origin_event_id": 4243]])))
        XCTAssertEqual(BlendPreview.readerAfter(alone, bareRevoke, eventId: id, now: 100.5), alone,
                       "a removed origin's bare revoke cannot move the scalar fence")
        XCTAssertEqual(try applyV2(alone, v2Wire()), alone, "the old session's v2 snapshot")
        let reopened = try opened(alone, session: "s2")
        XCTAssertEqual(try applyV2(reopened, v2Wire(session: "s2")), reopened, "a v2 snapshot of a fold the page no longer has")

        // Back into a fold: the resumed row's identity fences it; legacy frames
        // are a downgrade again; the scalar epoch was this row's, not the fold's.
        let refolded = try opened(BlendPreview.readerAfterMembership(newer, members: ["4242", "4244"]), session: "s3")
        XCTAssertEqual(refolded.epoch, -1)
        let joinBase: [String: Int] = ["4242": 10, "4244": 30]
        XCTAssertEqual(try applyV2(refolded, v2Wire(session: "s3", authority: ["4242": origin(100, 2), "4244": origin(7, 1)], base: joinBase), now: 100.6),
                       refolded, "an older own tuple cannot enter the fold")
        XCTAssertEqual(try applyV2(refolded, v2Wire(session: "s3", authority: ["4242": origin(100, 3), "4244": origin(7, 1)], base: joinBase), now: 100.6)
                           .held?.expiresAt, 101.5, "the same keeps its deadline")
        XCTAssertEqual(BlendPreview.readerAfter(refolded, singletonFrame(0.7, epoch: 100, seq: 4), eventId: id, now: 100.6), refolded,
                       "a singleton cannot stand in for the fold")
        XCTAssertEqual(BlendPreview.readerAfter(refolded, try foldedFrame(origin: 4244, epoch: 999, seq: 1, baseRev: 30, base: joinBase),
                                                eventId: id, now: 100.6), refolded, "nor can a v1 fold follow v2")

        // The v1 order whose origin is the page row becomes its own fence.
        let ownFold = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"]),
            try foldedFrame(origin: 4242, epoch: 900, seq: 2, baseRev: 10, base: ["4242": 10, "4243": 20]), eventId: id, now: 100)
        XCTAssertEqual(ownFold.held?.p, 0.6)
        let ownAlone = BlendPreview.readerAfterMembership(ownFold, members: ["4242"])
        XCTAssertNil(ownAlone.foldedSequence, "the v1 order is handed to the row")
        XCTAssertEqual(ownAlone.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101))
        XCTAssertEqual(ownAlone.epoch, 900, "the scalar epoch is still this row's domain")
        XCTAssertEqual(BlendPreview.readerAfter(ownAlone, singletonFrame(0.7, epoch: 900, seq: 1), eventId: id, now: 100.5), ownAlone)
        XCTAssertEqual(BlendPreview.readerAfter(ownAlone, singletonFrame(0.7, epoch: 900, seq: 2), eventId: id, now: 100.5).held?.expiresAt, 101)
        XCTAssertEqual(BlendPreview.readerAfter(ownAlone, singletonFrame(0.7, epoch: 900, seq: 3), eventId: id, now: 100.5).held?.seq, 3)
        XCTAssertEqual(BlendPreview.readerAfter(ownAlone, singletonFrame(0.7, epoch: 12, seq: 3), eventId: id, now: 100.5), ownAlone,
                       "an older epoch stays fenced")
        // The v1 order whose origin was the other row leaves with it; the
        // page's own epoch is admitted.
        let otherFold = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"]),
            try foldedFrame(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: ["4242": 10, "4243": 20]), eventId: id, now: 100)
        let otherAlone = BlendPreview.readerAfterMembership(otherFold, members: ["4242"])
        XCTAssertEqual(otherAlone.epoch, -1)
        XCTAssertNil(otherAlone.foldedSequence)
        XCTAssertEqual(otherAlone.retiredMembers, [BlendPreviewReader.RetiredMember(
            row: "4243", fence: BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101), floor: nil)],
            "the removed origin's order is its retired fence")
        XCTAssertEqual(BlendPreview.readerAfter(otherAlone, singletonFrame(0.7, epoch: 12, seq: 3), eventId: id, now: 100.5).held?.p, 0.7)

        // Singleton → fold: the page's singleton epoch was never the new
        // origin's domain (b9c8a143 fenced origin 4244's epoch 5 behind it).
        let singleOnly = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242"]),
                                                  singletonFrame(0.7, epoch: 12, seq: 3), eventId: id, now: 100)
        let joined = BlendPreview.readerAfterMembership(singleOnly, members: ["4242", "4244"])
        XCTAssertEqual(joined.epoch, -1)
        XCTAssertEqual(joined.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 12, seq: 3, retired: false, deadline: 101))
        XCTAssertEqual(BlendPreview.readerAfter(joined, try foldedFrame(origin: 4244, epoch: 5, seq: 1, baseRev: 30, base: joinBase),
                                                eventId: id, now: 100.2).held?.p, 0.6, "the other origin leads at its own epoch")
        XCTAssertEqual(BlendPreview.readerAfter(joined, try foldedFrame(origin: 4242, epoch: 11, seq: 9, baseRev: 10, base: joinBase),
                                                eventId: id, now: 100.2), joined, "an older own epoch cannot lead the fold")
        XCTAssertEqual(BlendPreview.readerAfter(joined, try foldedFrame(origin: 4242, epoch: 12, seq: 2, baseRev: 10, base: joinBase),
                                                eventId: id, now: 100.2), joined, "nor an older own seq")
        XCTAssertEqual(BlendPreview.readerAfter(joined, try foldedFrame(origin: 4242, epoch: 12, seq: 3, baseRev: 10, base: joinBase),
                                                eventId: id, now: 100.5).held?.expiresAt, 101, "the same tuple keeps its deadline")
        XCTAssertEqual(BlendPreview.readerAfter(joined, try foldedFrame(origin: 4242, epoch: 12, seq: 4, baseRev: 10, base: joinBase),
                                                eventId: id, now: 100.5).held?.expiresAt, 101.5)
    }

    /// On the v1 path the removed origin's order used to leave with nothing
    /// behind: a flap back admitted an older tuple of it at epoch −1. It is
    /// retired evidence now, like a fence or a floor.
    func testAV1OriginThatLeavesAndReturnsKeepsItsOrderAsAFence() throws {
        let base: [String: Int] = ["4242": 10, "4243": 20]
        let fold = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"]),
                                            try foldedFrame(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: base), eventId: id, now: 100)
        let away = BlendPreview.readerAfterMembership(fold, members: ["4242", "4244"])
        XCTAssertEqual(away.retiredMembers, [BlendPreviewReader.RetiredMember(
            row: "4243", fence: BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101), floor: nil)])
        let back = BlendPreview.readerAfterMembership(away, members: ["4242", "4243"])
        XCTAssertEqual(back.epoch, -1)
        XCTAssertEqual(back.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101))
        XCTAssertEqual(back.retiredMembers, [])
        XCTAssertEqual(BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 900, seq: 1, baseRev: 20, base: base), eventId: id, now: 100.3),
                       back, "an older tuple of the returning origin is refused")
        XCTAssertEqual(BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 12, seq: 9, baseRev: 20, base: base), eventId: id, now: 100.3),
                       back, "so is an older epoch")
        XCTAssertEqual(BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: base), eventId: id, now: 100.3)
                           .held?.expiresAt, 101, "the same tuple keeps its first-seen deadline")
        XCTAssertEqual(BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 900, seq: 3, baseRev: 20, base: base), eventId: id, now: 100.3)
                           .held?.seq, 3)
        // A retired (withdrawn) order returns retired.
        let withdrawn = BlendPreview.readerAfter(fold, try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": NSNull(),
            "preview": ["kind": "revoke", "epoch": 900, "seq": 3, "through_seq": 2, "origin_event_id": 4243]]))), eventId: id, now: 100.2)
        XCTAssertNil(withdrawn.held)
        let backRetired = BlendPreview.readerAfterMembership(
            BlendPreview.readerAfterMembership(withdrawn, members: ["4242", "4244"]), members: ["4242", "4243"])
        XCTAssertEqual(backRetired.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 3, retired: true, deadline: nil))
        XCTAssertEqual(BlendPreview.readerAfter(backRetired, try foldedFrame(origin: 4243, epoch: 900, seq: 3, baseRev: 20, base: base), eventId: id, now: 100.3),
                       backRetired, "the revoked tuple cannot return")
        XCTAssertEqual(BlendPreview.readerAfter(backRetired, try foldedFrame(origin: 4243, epoch: 900, seq: 4, baseRev: 20, base: base), eventId: id, now: 100.3)
                           .held?.seq, 4)
    }

    /// Remaining blocker 3: two-source probabilities can elect a different
    /// origin pair while a membership of three or more rows stays fixed. The
    /// server retires every origin of a session whose owner set changed and
    /// goes quiet until a fresh stream (`folded_blend_preview_v2.py`); on
    /// b9c8a143 the reader then refused the fresh stream for good, because the
    /// retained fences plus the new pair made three origins. Fences are per
    /// row within the membership now; election authority stays per session.
    func testAnElectionChangeInsideAnUnchangedMembershipResumesOnTheFreshStream() throws {
        let three: [String: Int] = ["4242": 10, "4243": 20, "4244": 30]
        let bound = BlendPreview.readerAfterMembership(try opened(), members: Set(three.keys))
        let first = try applyV2(bound, v2Wire(authority: ["4242": origin(100, 2), "4243": origin(2, 1)], base: three))
        XCTAssertEqual(first.held?.p, 0.65)
        XCTAssertEqual(first.sessionOrigins, ["4242", "4243"])
        // The server's last word on this session: every origin retired.
        let retiredAll = try applyV2(first, v2Wire(2, kind: "revoke", authority: [
            "4242": origin(100, 2, state: "revoked"), "4243": origin(2, 1, state: "revoked")], base: three), now: 100.2)
        XCTAssertNil(retiredAll.held)
        XCTAssertEqual(retiredAll.originFences["4243"]?.retired, true)
        let newPair: [String: Any] = ["4242": origin(100, 3), "4244": origin(7, 1)]
        XCTAssertEqual(try applyV2(retiredAll, v2Wire(3, authority: newPair, base: three), now: 100.3), retiredAll,
                       "election authority is per session: 4243 is unaccounted for")
        // The fresh stream elects 4242/4244 on the same membership.
        let fresh = try opened(BlendPreview.readerReset(retiredAll), session: "s2")
        XCTAssertEqual(fresh.foldMembers, Set(three.keys), "membership did not change")
        let elected = try applyV2(fresh, v2Wire(session: "s2", authority: newPair, base: three), now: 100.4)
        XCTAssertEqual(elected.held?.p, 0.65)
        XCTAssertEqual(elected.held?.expiresAt, 101.4)
        XCTAssertEqual(BlendPreview.displayed(elected.held, held: try detail(revision: three), now: 100.4), 0.65)
        XCTAssertEqual(Set(elected.originFences.keys), ["4242", "4243", "4244"], "every row's fence stays")
        XCTAssertEqual(elected.originFences["4243"]?.retired, true)
        XCTAssertEqual(elected.sessionOrigins, ["4242", "4244"])
        XCTAssertEqual(try applyV2(fresh, v2Wire(session: "s2", authority: ["4242": origin(100, 2), "4244": origin(7, 1)], base: three), now: 100.4),
                       fresh, "4242's retired tuple cannot return as pending")
        // A later flip back: 4243's fence still orders it.
        let again = try opened(BlendPreview.readerReset(elected), session: "s3")
        XCTAssertEqual(try applyV2(again, v2Wire(session: "s3", authority: ["4242": origin(100, 3), "4243": origin(2, 1)], base: three), now: 100.5),
                       again, "the revoked 4243 tuple cannot return")
        XCTAssertEqual(try applyV2(again, v2Wire(session: "s3", authority: ["4242": origin(100, 3), "4243": origin(2, 0)], base: three), now: 100.5),
                       again, "nor an older one")
        XCTAssertEqual(try applyV2(again, v2Wire(session: "s3", authority: ["4242": origin(100, 3), "4243": origin(2, 2)], base: three), now: 100.5)
                           .held?.p, 0.65)
        // The bound that replaced "two origins": a fence the frame's
        // membership does not cover is refused.
        var orphan = fresh; orphan.foldMembers = nil; orphan.authorityMembers = nil
        XCTAssertEqual(try applyV2(orphan, v2Wire(session: "s2", authority: ["4242": origin(100, 3), "4244": origin(7, 1)],
                                                  base: ["4242": 10, "4244": 30]), now: 100.4), orphan, "4243's fence is outside this base")
    }

    private func v1Revoke(origin: Int, epoch: Int, seq: Int, through: Int) throws -> BlendPreviewFrame {
        try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": NSNull(),
            "preview": ["kind": "revoke", "epoch": epoch, "seq": seq, "through_seq": through, "origin_event_id": origin]])))
    }

    /// Root's independent source review of a7dbdcbf (P1): the v1→v2 bridge
    /// imported the v1 order only when its origin had no fence. A returning
    /// origin gets its fence back (`readerAfterMembership`), so a v1 order
    /// accepted after the return — or that order's revocation — was never
    /// merged, and a new matching v2 session validated an older pending tuple
    /// against the restored, older fence. The order now merges monotonically
    /// into any existing fence before v2 validation: identity only moves
    /// forward, a same tuple keeps its first-seen deadline, retirement is
    /// sticky, and older evidence never overwrites a newer fence.
    func testNewerV1AuthorityMergesIntoARestoredFenceBeforeV2Validation() throws {
        let base: [String: Int] = ["4242": 10, "4243": 20]
        // Root's setup: 4243 (900,2) accepted at 100 (deadline 101), leaves, returns with its fence.
        let fold = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"]),
                                            try foldedFrame(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: base), eventId: id, now: 100)
        let back = BlendPreview.readerAfterMembership(
            BlendPreview.readerAfterMembership(fold, members: ["4242", "4244"]), members: ["4242", "4243"])
        XCTAssertEqual(back.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101))

        // Newer v1 (900,3) accepted at 100.3: the v1 path records the order; the fence still reads (900,2).
        let newerV1 = BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 900, seq: 3, baseRev: 20, base: base), eventId: id, now: 100.3)
        XCTAssertEqual(newerV1.held?.seq, 3)
        XCTAssertEqual(newerV1.foldedSequence, BlendPreviewReader.FoldedSequence(epoch: 900, seq: 3, originEventId: 4243))
        XCTAssertEqual(newerV1.originFences["4243"]?.seq, 2)

        // Newer v1, then an older v2 in a new matching session: refused.
        let session = try opened(newerV1, session: "s2")
        let olderV2 = v2Wire(session: "s2", authority: ["4243": origin(900, 2)], base: base)
        XCTAssertEqual(try applyV2(session, olderV2, now: 100.4), session, "(900,2) is older than the accepted v1 (900,3)")
        XCTAssertEqual(try applyV2(session, olderV2, now: 100.4).held?.seq, 3, "the live v1 (900,3) preview stands")
        let sameV2 = try applyV2(session, v2Wire(session: "s2", authority: ["4243": origin(900, 3)], base: base), now: 100.4)
        XCTAssertEqual(sameV2.held?.expiresAt, 101.3, "the same tuple keeps the v1 order's first-seen deadline")
        XCTAssertEqual(sameV2.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 3, retired: false, deadline: 101.3))
        // A genuinely newer v2 tuple is admitted, with its own deadline.
        let newerV2 = try applyV2(session, v2Wire(session: "s2", authority: ["4243": origin(900, 4)], base: base), now: 100.4)
        XCTAssertEqual(newerV2.held?.p, 0.65)
        XCTAssertEqual(newerV2.held?.expiresAt, 101.4)
        XCTAssertEqual(newerV2.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 4, retired: false, deadline: 101.4))
        XCTAssertEqual(BlendPreview.displayed(newerV2.held, held: try detail(), now: 100.4), 0.65)

        // Revoked v1 (seq 4 through 3), then an older v2: refused — the revoked
        // tuples, and the revoke's own sequence, never come back as pending.
        let revoked = BlendPreview.readerAfter(newerV1, try v1Revoke(origin: 4243, epoch: 900, seq: 4, through: 3), eventId: id, now: 100.35)
        XCTAssertNil(revoked.held)
        XCTAssertEqual(revoked.foldedSequence, BlendPreviewReader.FoldedSequence(epoch: 900, seq: 4, originEventId: 4243))
        XCTAssertEqual(revoked.originFences["4243"]?.seq, 2, "the restored fence is untouched until the bridge merges")
        let revokedSession = try opened(revoked, session: "s3")
        for seq in [2, 3, 4] {
            XCTAssertEqual(try applyV2(revokedSession, v2Wire(session: "s3", authority: ["4243": origin(900, seq)], base: base), now: 100.4),
                           revokedSession, "(900,\(seq)) cannot become pending after the revoke")
        }
        let resumed = try applyV2(revokedSession, v2Wire(session: "s3", authority: ["4243": origin(900, 5)], base: base), now: 100.4)
        XCTAssertEqual(resumed.held?.expiresAt, 101.4, "a genuinely newer v2 tuple resumes the fold")
        XCTAssertEqual(resumed.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 5, retired: false, deadline: 101.4))

        // The merge never overwrites a newer fence with older evidence (the
        // reader's own paths cannot produce an order older than the fence; the
        // state is set directly to pin the rule).
        var older = back
        older.foldedSequence = BlendPreviewReader.FoldedSequence(epoch: 900, seq: 1, originEventId: 4243)
        let olderSession = try opened(older, session: "s4")
        XCTAssertEqual(try applyV2(olderSession, v2Wire(session: "s4", authority: ["4243": origin(900, 1)], base: base), now: 100.4),
                       olderSession, "the older order does not lower the fence")
        let kept = try applyV2(olderSession, v2Wire(session: "s4", authority: ["4243": origin(900, 2)], base: base), now: 100.4)
        XCTAssertEqual(kept.held?.expiresAt, 101, "the newer fence and its first-seen deadline stand")
        XCTAssertEqual(kept.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 2, retired: false, deadline: 101))

        // Retirement is sticky in the merge: a fence retired at (900,3) stays
        // retired even with a live v1 order of the same tuple on display.
        let withdrawn = BlendPreview.readerAfter(fold, try v1Revoke(origin: 4243, epoch: 900, seq: 3, through: 2), eventId: id, now: 100.2)
        var sticky = BlendPreview.readerAfterMembership(
            BlendPreview.readerAfterMembership(withdrawn, members: ["4242", "4244"]), members: ["4242", "4243"])
        XCTAssertEqual(sticky.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 3, retired: true, deadline: nil))
        sticky.foldedSequence = BlendPreviewReader.FoldedSequence(epoch: 900, seq: 3, originEventId: 4243)
        sticky.held = BlendPreviewState(eventId: id, epoch: 900, seq: 3, baseRev: 20, p: 0.6, status: "live", expiresAt: 101.3,
                                        observedAt: nil, baseFoldRevision: FoldRevision(base), originEventId: 4243,
                                        pAway: 0.2, sport: "soccer_epl")
        let stickySession = try opened(sticky, session: "s5")
        XCTAssertEqual(try applyV2(stickySession, v2Wire(session: "s5", authority: ["4243": origin(900, 3)], base: base), now: 100.4),
                       stickySession, "the retired tuple cannot become pending")
        XCTAssertEqual(try applyV2(stickySession, v2Wire(session: "s5", authority: ["4243": origin(900, 4)], base: base), now: 100.4)
                           .originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 4, retired: false, deadline: 101.4))

        // The page row's own v1 order merges into its singleton fence the same way.
        let joinBase: [String: Int] = ["4242": 10, "4244": 30]
        let joined = BlendPreview.readerAfterMembership(
            BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242"]),
                                     singletonFrame(0.7, epoch: 12, seq: 3), eventId: id, now: 100),
            members: ["4242", "4244"])
        let ownOrder = BlendPreview.readerAfter(joined, try foldedFrame(origin: 4242, epoch: 12, seq: 4, baseRev: 10, base: joinBase), eventId: id, now: 100.2)
        XCTAssertEqual(ownOrder.held?.seq, 4)
        XCTAssertEqual(ownOrder.originFences["4242"]?.seq, 3)
        let ownSession = try opened(ownOrder, session: "s6")
        XCTAssertEqual(try applyV2(ownSession, v2Wire(session: "s6", authority: ["4242": origin(12, 3), "4244": origin(7, 1)], base: joinBase), now: 100.4),
                       ownSession, "the own row's older tuple is refused")
        XCTAssertEqual(try applyV2(ownSession, v2Wire(session: "s6", authority: ["4242": origin(12, 4), "4244": origin(7, 1)], base: joinBase), now: 100.4)
                           .held?.expiresAt, 101.2, "the same keeps the v1 order's deadline")
        XCTAssertEqual(try applyV2(ownSession, v2Wire(session: "s6", authority: ["4242": origin(12, 5), "4244": origin(7, 1)], base: joinBase), now: 100.4)
                           .held?.expiresAt, 101.4)
    }

    /// Root's independent source review of a7dbdcbf (P2): rows can leave a
    /// fold together, and every departing row is retired before the capacity
    /// check, so the retired list is NOT bounded by `maxRetiredMembers + 1`.
    /// The actual behaviour, pinned here: nothing is ever dropped; at
    /// saturation the list holds every previously retired row plus every row
    /// that left in that transition, and then freezes. Saturation is a loss of
    /// preview coverage for the rest of the visit, not continuous delivery.
    func testRowsThatLeaveTogetherAreAllRetainedAndCanExceedCapacityPlusOne() throws {
        func entry(_ reader: BlendPreviewReader, _ row: String) -> BlendPreviewReader.RetiredMember? {
            reader.retiredMembers.first { $0.row == row }
        }
        // Each fold: the page row with two elected origins, a floor on every row.
        func folded(_ reader: BlendPreviewReader, _ a: String, _ b: String) throws -> BlendPreviewReader {
            let members: Set<String> = ["4242", a, b]
            let base: [String: Int] = ["4242": 10, a: 5, b: 5]
            var next = try opened(BlendPreview.readerAfterMembership(reader, members: members), session: "s-\(a)")
            next = try applyV2(next, v2Wire(session: "s-\(a)", authority: [a: origin(1, 1), b: origin(3, 1)], base: base))
            XCTAssertEqual(next.held?.p, 0.65, "\(a)/\(b)")
            return BlendPreview.readerAfterCommitFloor(next, FoldRevision(base))
        }
        let fenceA = BlendPreviewReader.OriginFence(epoch: 1, seq: 1, retired: false, deadline: 101)
        let fenceB = BlendPreviewReader.OriginFence(epoch: 3, seq: 1, retired: false, deadline: 101)

        // Two rows leave together, below capacity: both are retired with fence and floor.
        var current = try folded(.empty, "4243", "4244")
        current = try folded(current, "4245", "4246")
        XCTAssertEqual(Set(current.retiredMembers.map(\.row)), ["4243", "4244"])
        XCTAssertEqual(entry(current, "4243"), BlendPreviewReader.RetiredMember(row: "4243", fence: fenceA, floor: 5))
        XCTAssertEqual(entry(current, "4244"), BlendPreviewReader.RetiredMember(row: "4244", fence: fenceB, floor: 5))
        XCTAssertEqual(current.floors?.rows, ["4242": 10, "4245": 5, "4246": 5])
        XCTAssertEqual(current.evidenceSaturated, false)

        // Up to capacity in pairs: 8 distinct retired rows is at capacity, not past it.
        current = try folded(current, "4247", "4248")
        current = try folded(current, "4249", "4250")
        current = try folded(current, "4251", "4252")
        XCTAssertEqual(current.retiredMembers.count, BlendPreviewReader.maxRetiredMembers)
        XCTAssertEqual(current.evidenceSaturated, false)

        // The saturating transition retires two rows at once: the list holds
        // maxRetiredMembers + 2 — past the single-departure maxRetiredMembers + 1 —
        // with every row's evidence, and the reader saturates.
        let saturated = BlendPreview.readerAfterMembership(current, members: ["4242", "4253"])
        XCTAssertEqual(saturated.evidenceSaturated, true)
        XCTAssertEqual(saturated.retiredMembers.count, BlendPreviewReader.maxRetiredMembers + 2, "nothing dropped")
        XCTAssertEqual(Set(saturated.retiredMembers.map(\.row)),
                       ["4243", "4244", "4245", "4246", "4247", "4248", "4249", "4250", "4251", "4252"])
        for row in ["4243", "4245", "4247", "4249", "4251"] {
            XCTAssertEqual(entry(saturated, row), BlendPreviewReader.RetiredMember(row: row, fence: fenceA, floor: 5), row)
        }
        for row in ["4244", "4246", "4248", "4250", "4252"] {
            XCTAssertEqual(entry(saturated, row), BlendPreviewReader.RetiredMember(row: row, fence: fenceB, floor: 5), row)
        }
        XCTAssertNil(saturated.held)
        XCTAssertNil(saturated.foldSession)
        XCTAssertEqual(saturated.originFences, [:])
        XCTAssertEqual(saturated.floors?.rows, ["4242": 10])

        // Coverage limit for the rest of the visit: nothing is admitted and
        // nothing moves — not a new fold, not a returning row's evidence, not
        // the legacy path; a reset keeps the limit. Committed truth shows.
        let refused = try applyV2(try opened(saturated, session: "s-4253"),
                                  v2Wire(session: "s-4253", authority: ["4253": origin(1, 1)], base: ["4242": 10, "4253": 5]), now: 100.4)
        XCTAssertNil(refused.held)
        XCTAssertEqual(refused.originFences, [:])
        let returning = BlendPreview.readerAfterMembership(saturated, members: ["4242", "4243", "4244"])
        XCTAssertEqual(returning.evidenceSaturated, true)
        XCTAssertEqual(returning.retiredMembers, saturated.retiredMembers, "the list is frozen")
        XCTAssertEqual(returning.originFences, [:], "a returning row's evidence stays retired")
        XCTAssertNil(try applyV2(try opened(returning, session: "s-again"),
                                 v2Wire(session: "s-again", authority: ["4243": origin(1, 2), "4244": origin(3, 2)],
                                        base: ["4242": 10, "4243": 5, "4244": 5]), now: 100.4).held)
        XCTAssertEqual(BlendPreview.readerReset(saturated).evidenceSaturated, true)
        XCTAssertEqual(BlendPreview.readerReset(saturated).retiredMembers, saturated.retiredMembers)
        XCTAssertEqual(BlendPreview.readerAfter(saturated, singletonFrame(0.7, epoch: 1, seq: 1), eventId: id, now: 100.4), saturated)
        XCTAssertNil(BlendPreview.displayed(saturated.held, held: try detail(revision: ["4242": 10, "4253": 5]), now: 100.4),
                     "the page shows committed truth")
    }

}
