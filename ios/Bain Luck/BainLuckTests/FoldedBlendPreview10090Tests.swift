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
    // MARK: - Authoritative membership changes (#10090 native v1 continuity)

    /// The backend's folded projection (`FoldedPreviewBase.project`) of one
    /// origin row's ledger frame, on this page.
    private func folded(origin: Int, epoch: Int, seq: Int, base: [String: Int],
                        ttl: Int = 1_000) throws -> BlendPreviewFrame {
        try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": 0.6, "p_away": 0.2,
            "sport": "soccer_epl", "status": "live", "display_observed_at": observed,
            "preview": ["kind": "blend", "epoch": epoch, "seq": seq, "base_rev": base[String(origin)]!,
                        "ttl_ms": ttl, "folded_version": 1, "origin_event_id": origin,
                        "base_fold_revision": base]])))
    }

    /// The unfolded route's raw singleton preview of this page's own row.
    private func singleton(epoch: Int, seq: Int, ttl: Int = 1_000) throws -> BlendPreviewFrame {
        try XCTUnwrap(BlendPreviewFrame.decode(raw(["event_id": id, "p": 0.7, "status": "live",
            "preview": ["kind": "blend", "epoch": epoch, "seq": seq, "base_rev": 10, "ttl_ms": ttl]])))
    }

    /// The page adopts `revision` as its authoritative detail fold.
    private func adopt(_ r: BlendPreviewReader, _ revision: [String: Int]) throws -> BlendPreviewReader {
        BlendPreview.readerAfterMembership(
            r, LiveEventPriceReconciliation.pairedFoldRevision(in: try detail(revision: revision)))
    }

    private func read(_ r: BlendPreviewReader, _ f: BlendPreviewFrame, at: TimeInterval) -> BlendPreviewReader {
        BlendPreview.readerAfter(r, f, eventId: id, now: at)
    }

    private let ab = ["4242": 10, "4243": 20]
    private let ac = ["4242": 10, "4244": 30]

    func testAMembershipChangeRetiresTheRemovedRowsFloorWithoutForgettingIt() throws {
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4243, epoch: 5, seq: 1, base: ab), at: 100)
        r = BlendPreview.readerAfterCommitFloor(r, raw: #"{"event_id":4242,"floor":{"4242":10,"4243":21}}"#, eventId: id)
        XCTAssertNil(r.held)
        XCTAssertEqual(BlendPreview.membershipChanges(r, FoldRevision(ab)), false)
        XCTAssertEqual(BlendPreview.membershipChanges(r, FoldRevision(ac)), true)
        r = try adopt(r, ac)
        XCTAssertEqual(r.members, ["4242", "4244"])
        XCTAssertEqual(r.floors?.rows, ["4242": 10, "4243": 21], "the removed row's floor is kept, not erased")
        r = read(r, try folded(origin: 4244, epoch: 5, seq: 1, base: ac), at: 101)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ac), now: 101), 0.6,
                       "the new fold is no longer withheld by a row it does not contain")
        XCTAssertEqual(r.held?.expiresAt, 102)
        // A frame still composed for the old membership never applies.
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 5, seq: 2, base: ab), at: 101.1), r)
        // A member's floor still withdraws; a non-member's no longer can.
        XCTAssertEqual(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 99])).held, r.held)
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4244": 31])).held)
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4242": 11])).held)
    }

    func testAnotherOriginsEpochNeverFencesTheReplacementOrigin() throws {
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4243, epoch: 900, seq: 2, base: ab), at: 100)
        XCTAssertEqual(r.epoch, -1, "another row's epoch is not the page row's floor")
        r = try adopt(r, ac)
        XCTAssertNil(r.held, "the old fold's preview is withdrawn at the boundary")
        r = read(r, try folded(origin: 4244, epoch: 12, seq: 81, base: ac), at: 100.2)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ac), now: 100.2), 0.6)
        XCTAssertEqual(r.originFences[4243], .init(epoch: 900, seq: 2), "the removed origin's fence is retained")
        // Ordering within the replacement origin is unchanged.
        for stale in [try folded(origin: 4244, epoch: 12, seq: 81, base: ac),
                      try folded(origin: 4244, epoch: 12, seq: 80, base: ac),
                      try folded(origin: 4244, epoch: 11, seq: 99, base: ac)] {
            XCTAssertEqual(read(r, stale, at: 100.3), r)
        }
        XCTAssertEqual(read(r, try folded(origin: 4244, epoch: 12, seq: 82, base: ac), at: 100.3).held?.seq, 82)
        // Steady state: two owning rows of one fold order independently too.
        var both = try adopt(.empty, ab)
        both = read(both, try folded(origin: 4243, epoch: 900, seq: 2, base: ab), at: 100)
        both = read(both, try folded(origin: 4242, epoch: 3, seq: 7, base: ab), at: 100.1)
        XCTAssertEqual(both.held?.originEventId, 4242)
        XCTAssertEqual(both.epoch, 3)
        XCTAssertEqual(read(both, try folded(origin: 4242, epoch: 3, seq: 6, base: ab), at: 100.2), both)
        let ownHigh = read(try adopt(.empty, ab), try folded(origin: 4242, epoch: 900, seq: 1, base: ab), at: 100)
        XCTAssertEqual(read(ownHigh, try folded(origin: 4243, epoch: 12, seq: 1, base: ab), at: 100.1).held?.originEventId,
                       4243, "nor does the page row's own epoch fence another row")
        // Neither a lower seq nor a withdrawal of one row speaks for the other's.
        var shared = try adopt(.empty, ab)
        shared = read(shared, try folded(origin: 4242, epoch: 5, seq: 1, base: ab), at: 100)
        shared = read(shared, try folded(origin: 4243, epoch: 5, seq: 9, base: ab), at: 100.1)
        shared = read(shared, try folded(origin: 4242, epoch: 5, seq: 3, base: ab), at: 100.2)
        XCTAssertEqual(shared.held?.originEventId, 4242, "the later arrival of the other row is shown")
        XCTAssertEqual(shared.held?.seq, 3)
        let withdrawal = BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke, epoch: 5, seq: 10,
                                           throughSeq: 9, originEventId: 4243)
        XCTAssertEqual(read(shared, withdrawal, at: 100.3).held?.seq, 3)
    }

    func testASingletonsAcceptedIdentityStillFencesTheFoldAfterAReset() throws {
        let a = ["4242": 10]
        var r = try adopt(.empty, a)
        r = read(r, try singleton(epoch: 100, seq: 2), at: 100)
        XCTAssertEqual(r.held?.expiresAt, 101)
        r.held = nil // disconnect / resync
        r = try adopt(r, ab)
        for stale in [try folded(origin: 4242, epoch: 100, seq: 1, base: ab),
                      try folded(origin: 4242, epoch: 100, seq: 2, base: ab),
                      try folded(origin: 4242, epoch: 99, seq: 9, base: ab)] {
            XCTAssertNil(read(r, stale, at: 100.5).held, "an older or the same identity gets no new lease")
        }
        XCTAssertEqual(read(r, try folded(origin: 4242, epoch: 100, seq: 3, base: ab), at: 100.5).held?.expiresAt, 101.5,
                       "a newer identity of the same ledger is admitted")
        // A revoked singleton identity stays revoked through the upgrade.
        var revoked = try adopt(.empty, a)
        revoked = read(revoked, try singleton(epoch: 100, seq: 2), at: 100)
        revoked = read(revoked, BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke,
                                                  epoch: 100, seq: 3, throughSeq: 2), at: 100.1)
        XCTAssertNil(revoked.held)
        revoked = try adopt(revoked, ab)
        XCTAssertNil(read(revoked, try folded(origin: 4242, epoch: 100, seq: 3, base: ab), at: 100.2).held)
        XCTAssertEqual(read(revoked, try folded(origin: 4242, epoch: 100, seq: 4, base: ab), at: 100.2).held?.seq, 4)
    }

    func testARowThatLeavesAndReturnsKeepsItsFenceAndFloor() throws {
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4242, epoch: 5, seq: 7, base: ab), at: 100)
        r = read(r, try folded(origin: 4243, epoch: 900, seq: 5, base: ab), at: 100.1)
        r = BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 21]))
        r = try adopt(r, ac) // e.g. a cached detail, then the fresh one, then cached again
        r = read(r, try folded(origin: 4244, epoch: 12, seq: 1, base: ac), at: 100.2)
        XCTAssertEqual(r.held?.originEventId, 4244)
        XCTAssertEqual(read(r, try folded(origin: 4242, epoch: 5, seq: 7, base: ac), at: 100.3), r,
                       "the surviving row's order carries across the change")
        XCTAssertEqual(read(r, try folded(origin: 4242, epoch: 5, seq: 8, base: ac), at: 100.3).held?.seq, 8)
        r = try adopt(r, ab)
        XCTAssertNil(r.held)
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 900, seq: 5, base: ab), at: 100.4), r,
                       "the returned row's old identity is not granted a new lease")
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 899, seq: 50, base: ab), at: 100.4), r)
        XCTAssertNil(read(r, try folded(origin: 4243, epoch: 900, seq: 6, base: ab), at: 100.4).held,
                     "nor is a newer one on a base its kept commit floor has passed")
        let rebased = ["4242": 10, "4243": 21]
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 900, seq: 6, base: rebased), at: 100.4).held?.seq, 6)
    }

    func testResetAndAnUnchangedMembershipRenewNothing() throws {
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4243, epoch: 5, seq: 1, base: ab), at: 100)
        XCTAssertEqual(try adopt(r, ab), r, "an unchanged membership changes nothing, the preview included")
        XCTAssertEqual(BlendPreview.readerAfterMembership(r, nil), r, "an absent fold makes no claim")
        let first = BlendPreview.readerAfterMembership(read(.empty, try folded(origin: 4243, epoch: 5, seq: 1, base: ab), at: 100),
                                                       FoldRevision(ab))
        XCTAssertEqual(first.held?.seq, 1, "the first membership is recorded, not a change")
        r = try adopt(r, ac)
        r.held = nil // an ordinary reconnect after the change keeps every fence
        r = try adopt(r, ab)
        XCTAssertNil(read(r, try folded(origin: 4243, epoch: 5, seq: 1, base: ab), at: 200).held)
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 5, seq: 2, base: ab), at: 200).held?.expiresAt, 201)
    }

    func testAFoldCollapsingToThePagesRowContinuesOnItsOwnLedger() throws {
        let a = ["4242": 10]
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4242, epoch: 7, seq: 2, base: ab), at: 100)
        r = read(r, try folded(origin: 4243, epoch: 900, seq: 1, base: ab), at: 100.1)
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 3), at: 100.2), r,
                       "a singleton never applies to a two-row page")
        r = try adopt(r, a)
        for stale in [try singleton(epoch: 7, seq: 2), try singleton(epoch: 7, seq: 1), try singleton(epoch: 6, seq: 9)] {
            XCTAssertEqual(read(r, stale, at: 100.3), r, "the row's accepted identity still fences")
        }
        r = read(r, try singleton(epoch: 7, seq: 3), at: 100.3)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: a), now: 100.3), 0.7)
        r.held = nil // reconnect: after folded authority a replay never renews
        XCTAssertNil(read(r, try singleton(epoch: 7, seq: 3), at: 100.4).held)
        XCTAssertNil(read(r, try folded(origin: 4242, epoch: 7, seq: 4, base: ab), at: 100.4).held,
                     "an old fold's frame is refused on the collapsed page")
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 4), at: 100.4).held?.seq, 4)
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
