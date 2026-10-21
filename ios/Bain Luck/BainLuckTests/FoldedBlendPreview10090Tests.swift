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
        XCTAssertEqual(pruned.epoch, 5, "the legacy epoch floor stays")
        let admitted = BlendPreview.readerAfter(pruned, v1New, eventId: id, now: 100.2)
        XCTAssertEqual(admitted.held?.p, 0.6)
        XCTAssertEqual(BlendPreview.displayed(admitted.held, held: try detail(revision: ["4242": 10, "4244": 30]), now: 100.2), 0.6)
        XCTAssertEqual(BlendPreview.readerAfter(pruned, try frame(seq: 3), eventId: id, now: 100.2), pruned,
                       "the old fold's v1 frame (4242/4243) is refused outright")
    }

}
