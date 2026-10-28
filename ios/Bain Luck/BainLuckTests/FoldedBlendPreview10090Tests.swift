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

    /// The page adopts `revision` as its authoritative detail fold, as
    /// `EventDetailViewModel.adopt` does: a detail without a fold makes no claim.
    private func adopt(_ r: BlendPreviewReader, _ revision: [String: Int]) throws -> BlendPreviewReader {
        adopt(r, LiveEventPriceReconciliation.pairedFoldRevision(in: try detail(revision: revision)))
    }

    private func adopt(_ r: BlendPreviewReader, _ revision: FoldRevision?) -> BlendPreviewReader {
        revision.map { BlendPreview.readerAfterMembership(r, members: Set($0.rows.keys)) } ?? r
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
        XCTAssertEqual(BlendPreview.membershipChanges(r, members: Set(ab.keys)), false)
        XCTAssertEqual(BlendPreview.membershipChanges(r, members: Set(ac.keys)), true)
        r = try adopt(r, ac)
        XCTAssertEqual(r.authorityMembers, ["4242", "4244"])
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4243" }?.floor, 21, "the removed row's floor is kept, not erased")
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
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4243" }?.fence.map { [$0.epoch, $0.seq] }, [900, 2],
                       "the removed origin's fence is retained")
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
        XCTAssertEqual(adopt(r, nil as FoldRevision?), r, "an absent fold makes no claim")
        let first = adopt(read(.empty, try folded(origin: 4243, epoch: 5, seq: 1, base: ab), at: 100),
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
        // #11105: joined with a frame, the 19:59 minute is drawn at its end
        // (20:00:00), still before the preview at 20:00:04.
        XCTAssertEqual(shown.filter { $0.source == "aggregate" }.map(\.date),
                       [served[0].date.addingTimeInterval(60), observed.asDate!])
        XCTAssertEqual(shown.filter { $0.source == "aggregate" }.first?.probability, served[0].probability)
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
                        base: [String: Int] = ["4242": 10, "4243": 20], p: Double = 0.65) -> [String: Any] {
        ["event_id": id, "p": kind == "blend" ? (p as Any) : (NSNull() as Any), "p_away": 0.2,
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
        XCTAssertEqual(fold2.epoch, -1, "the scalar epoch is the page row's alone (f211)")
        XCTAssertEqual(fold2.legacyOrders["4243"], BlendPreviewReader.FoldedSequence(epoch: 900, seq: 2, originEventId: 4243),
                       "origin 4243's epoch 900 is its own order")
        XCTAssertEqual(fold2.held?.p, 0.6)
        let origin3 = try folded(origin: 4244, epoch: 12, seq: 81, baseRev: 30, base: ["4242": 10, "4244": 30])
        let reset = BlendPreview.readerReset(fold2)
        XCTAssertEqual(BlendPreview.readerAfter(reset, origin3, eventId: id, now: 100.2), reset,
                       "reset is not a boundary: origin 4244 is not in the authoritative fold, so its frame is still refused")
        let pruned = BlendPreview.readerAfterMembership(fold2, members: ["4242", "4244"])
        XCTAssertEqual(pruned.epoch, -1)
        XCTAssertNil(pruned.foldedSequence)
        let admitted = BlendPreview.readerAfter(pruned, origin3, eventId: id, now: 100.2)
        XCTAssertEqual(admitted.epoch, -1, "the replacement origin's epoch is not the page row's scalar")
        XCTAssertEqual(admitted.legacyOrders["4244"], BlendPreviewReader.FoldedSequence(epoch: 12, seq: 81, originEventId: 4244),
                       "the replacement origin's own order is the fence now")
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

    /// Native's step 4 on f1da49c1 (f211's page test
    /// `AMembershipChangeReopensTheV1FoldedPreview10090Tests`, L135): a v1
    /// tuple shown when its row leaves carries its first-seen deadline away
    /// with it, and returning at once it continues under it
    /// (`testAV1OriginThatLeavesAndReturnsKeepsItsOrderAsAFence`). That lease
    /// only continues the display the boundary interrupted. v1 shows one frame
    /// at a time, so once a later v1 blend of another row is accepted the
    /// lease is spent: a replay of the tuple after the flap back is refused
    /// (v1 never replays), a newer tuple still leads, and the fence v2 reads
    /// keeps the lease. The page test's reader sequence, flap after advance.
    func testACarriedV1LeaseIsSpentByALaterBlendOfAnotherRow() throws {
        var r = try adopt(.empty, ab)
        r = read(r, try folded(origin: 4243, epoch: 900, seq: 1, base: ab), at: 100)
        r = BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 21]))
        XCTAssertNil(r.held)
        r = try adopt(r, ac)
        r = read(r, try folded(origin: 4244, epoch: 12, seq: 1, base: ac), at: 100.1)
        XCTAssertEqual(r.held?.originEventId, 4244)
        r = try adopt(r, ab) // a cached detail flaps back while 4244's tuple is shown
        let lease = BlendPreviewReader.OriginFence(epoch: 12, seq: 1, retired: false, deadline: 101.1)
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4244" }?.fence, lease)
        let atOnce = try adopt(r, ac)
        XCTAssertEqual(read(atOnce, try folded(origin: 4244, epoch: 12, seq: 1, base: ac), at: 100.3).held?.expiresAt, 101.1,
                       "back at once, the same tuple continues under its first-seen deadline")
        XCTAssertEqual(read(r, try folded(origin: 4243, epoch: 900, seq: 1, base: ab), at: 100.2), r,
                       "the returned row's old identity gets no new lease")
        r = read(r, try folded(origin: 4243, epoch: 900, seq: 3, base: ab), at: 100.2)
        XCTAssertNil(r.held, "a later 4243 blend is accepted, and withdrawn by its kept commit floor")
        r = BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4244": 30])) // the away row's floor merges into its evidence
        r = try adopt(r, ac) // the fresh detail returns
        XCTAssertEqual(read(r, try folded(origin: 4244, epoch: 12, seq: 1, base: ac), at: 100.3), r,
                       "the replayed identity stays fenced across the flap")
        XCTAssertEqual(read(r, try folded(origin: 4244, epoch: 12, seq: 2, base: ac), at: 100.3).held?.expiresAt, 101.3,
                       "a newer tuple of the row still leads")
        XCTAssertEqual(r.originFences["4244"], lease, "the fence v2 reads is untouched")
        XCTAssertEqual(try applyV2(opened(r, session: "s2"), v2Wire(session: "s2", authority: ["4244": origin(12, 1)], base: ac),
                                   now: 100.3).held?.expiresAt, 101.1, "and v2 keeps the same-tuple lease")

        // A surviving row's lease is spent the same way. 4242's tuple is shown
        // at the boundary; back at once it continues, after 4244's blend it is
        // a replay.
        var s = try adopt(.empty, ab)
        s = read(s, try folded(origin: 4242, epoch: 5, seq: 7, base: ab), at: 100)
        s = try adopt(s, ac)
        XCTAssertEqual(s.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 5, seq: 7, retired: false, deadline: 101))
        XCTAssertEqual(read(s, try folded(origin: 4242, epoch: 5, seq: 7, base: ac), at: 100.2).held?.expiresAt, 101,
                       "the surviving row's shown tuple continues under its deadline")
        s = read(s, try folded(origin: 4244, epoch: 12, seq: 1, base: ac), at: 100.1)
        XCTAssertEqual(s.held?.originEventId, 4244)
        XCTAssertEqual(read(s, try folded(origin: 4242, epoch: 5, seq: 7, base: ac), at: 100.2), s,
                       "after another row's blend the surviving row's tuple is a replay")
        XCTAssertEqual(read(s, try folded(origin: 4242, epoch: 5, seq: 8, base: ac), at: 100.2).held?.seq, 8)
        XCTAssertEqual(s.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 5, seq: 7, retired: false, deadline: 101))
        // Another row's withdrawal says nothing about the lease (`previewAfter`).
        let three = ["4242": 10, "4243": 20, "4245": 50], next = ["4242": 10, "4243": 20, "4244": 30]
        var w = read(read(try adopt(.empty, three), try folded(origin: 4243, epoch: 900, seq: 1, base: three), at: 100),
                     try folded(origin: 4242, epoch: 5, seq: 7, base: three), at: 100.1)
        w = try adopt(w, next)
        w = read(w, try v1Revoke(origin: 4243, epoch: 900, seq: 2, through: 1), at: 100.2)
        XCTAssertEqual(w.legacyOrders["4243"], BlendPreviewReader.FoldedSequence(epoch: 900, seq: 2, originEventId: 4243))
        XCTAssertEqual(read(w, try folded(origin: 4242, epoch: 5, seq: 7, base: next), at: 100.3).held?.expiresAt, 101.1)
        // A spent lease never lowers a newer v1 order the row already holds.
        var o = BlendPreview.readerAfterMembership(read(try adopt(.empty, ["4242": 10]), try singleton(epoch: 12, seq: 3), at: 100),
                                                   members: ["4242", "4244"])
        o = read(o, try folded(origin: 4242, epoch: 12, seq: 4, base: ac), at: 100.1)
        o = read(o, try folded(origin: 4244, epoch: 7, seq: 1, base: ac), at: 100.2)
        XCTAssertEqual(o.legacyOrders["4242"], BlendPreviewReader.FoldedSequence(epoch: 12, seq: 4, originEventId: 4242))
        XCTAssertEqual(read(o, try folded(origin: 4242, epoch: 12, seq: 4, base: ac), at: 100.3), o)
        // After v2 authority the fences are v2's: a singleton the folded-down
        // page row accepts spends nothing, and a row that returns keeps its v2
        // lease across a later flap.
        var v = try applyV2(try adopt(opened(), ab), v2Wire(authority: ["4242": origin(7, 2), "4243": origin(900, 1)]), now: 100.1)
        v = read(try adopt(v, ["4242": 10]), try singleton(epoch: 7, seq: 3), at: 100.3)
        XCTAssertEqual(v.held?.seq, 3)
        v = try adopt(try adopt(try adopt(v, ab), ac), ab)
        XCTAssertEqual(try applyV2(opened(v, session: "s2"), v2Wire(session: "s2", authority: ["4243": origin(900, 1)]), now: 100.4)
                           .held?.expiresAt, 101.1)
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

    /// Root's correction-delta review of d1bdda77 (P1): the bridge re-ran on
    /// every v2 frame while the v1 order stayed in the reader. After the first
    /// accepted v2 frame the display is a v2 composite with no legacy origin,
    /// so the next frame's bridge read "no held v1 value" as the tuple having
    /// retired, made that sticky, and refused the still-pending origin — and
    /// the sibling's legitimate update with it. The first accepted v2 frame
    /// now consumes the order: the fence is the record from then on, for every
    /// later frame, reset, reconnect and membership boundary. Before a frame is
    /// accepted the order stays and every attempt reads the current display.
    func testASuccessfulV2MigrationConsumesTheLegacyOrderAndKeepsTheOriginPending() throws {
        let base: [String: Int] = ["4242": 10, "4243": 20]
        let fold = BlendPreview.readerAfter(BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"]),
                                            try foldedFrame(origin: 4243, epoch: 900, seq: 2, baseRev: 20, base: base), eventId: id, now: 100)
        let back = BlendPreview.readerAfterMembership(
            BlendPreview.readerAfterMembership(fold, members: ["4242", "4244"]), members: ["4242", "4243"])
        let newerV1 = BlendPreview.readerAfter(back, try foldedFrame(origin: 4243, epoch: 900, seq: 3, baseRev: 20, base: base), eventId: id, now: 100.3)
        XCTAssertEqual(newerV1.held?.expiresAt, 101.3)

        // Migration: the first accepted v2 frame merges and consumes the order.
        let session = try opened(newerV1, session: "s2")
        let migrated = try applyV2(session, v2Wire(session: "s2", authority: ["4243": origin(900, 3), "4242": origin(12, 2)], base: base), now: 100.4)
        XCTAssertEqual(migrated.foldSeq, 1)
        XCTAssertEqual(migrated.held?.p, 0.65)
        XCTAssertEqual(migrated.held?.expiresAt, 101.3, "the bridged origin keeps the v1 order's first-seen deadline")
        XCTAssertEqual(migrated.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 3, retired: false, deadline: 101.3))
        XCTAssertEqual(migrated.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 12, seq: 2, retired: false, deadline: 101.4))
        XCTAssertNil(migrated.foldedSequence, "the order is consumed")

        // A sibling-only update while the bridged origin stays pending: admitted,
        // the fold sequence advances, 4243's pending state and deadline are kept.
        let siblingUpdate = v2Wire(2, session: "s2", authority: ["4243": origin(900, 3), "4242": origin(12, 3)], base: base, p: 0.66)
        let updated = try applyV2(migrated, siblingUpdate, now: 100.5)
        XCTAssertEqual(updated.foldSeq, 2)
        XCTAssertEqual(updated.held?.p, 0.66)
        XCTAssertEqual(updated.held?.expiresAt, 101.3)
        XCTAssertEqual(updated.originFences["4243"], migrated.originFences["4243"], "still pending, same deadline")
        XCTAssertEqual(updated.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 12, seq: 3, retired: false, deadline: 101.5))
        XCTAssertEqual(BlendPreview.displayed(updated.held, held: try detail(), now: 100.5), 0.66)

        // The same tuple stays limited to its original deadline; a newer tuple resumes.
        let sameAgain = v2Wire(3, session: "s2", authority: ["4243": origin(900, 3), "4242": origin(12, 3)], base: base)
        XCTAssertEqual(try applyV2(updated, sameAgain, now: 101.35), updated, "(900,3) expired at 101.3")
        XCTAssertEqual(try applyV2(updated, v2Wire(3, session: "s2", authority: ["4243": origin(900, 4), "4242": origin(12, 3)], base: base), now: 101.35)
                           .held?.expiresAt, 101.5, "a newer 4243 tuple resumes; 4242 keeps its own deadline")

        // An actual v2 revoke, then the same tuple pending again: refused — in
        // the session and after a reconnect; a newer tuple is admitted.
        let revoked = try applyV2(updated, v2Wire(3, session: "s2", kind: "revoke", authority: [
            "4243": origin(900, 3, state: "revoked"), "4242": origin(12, 3, state: "revoked")], base: base), now: 100.6)
        XCTAssertNil(revoked.held)
        XCTAssertEqual(revoked.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 3, retired: true, deadline: 101.3))
        XCTAssertEqual(try applyV2(revoked, v2Wire(4, session: "s2", authority: ["4243": origin(900, 3), "4242": origin(12, 4)], base: base), now: 100.7),
                       revoked, "the revoked tuple cannot become pending")
        let afterRevoke = try opened(BlendPreview.readerReset(revoked), session: "s3")
        XCTAssertEqual(try applyV2(afterRevoke, v2Wire(session: "s3", authority: ["4243": origin(900, 3), "4242": origin(12, 4)], base: base), now: 100.7),
                       afterRevoke, "nor after a reconnect")
        XCTAssertEqual(try applyV2(afterRevoke, v2Wire(session: "s3", authority: ["4243": origin(900, 4), "4242": origin(12, 4)], base: base), now: 100.7)
                           .held?.expiresAt, 101.7)

        // A reconnect after migration keeps the per-origin fences as they are:
        // the same tuples are admitted up to their first-seen deadlines, older ones refused.
        let reconnected = try opened(BlendPreview.readerReset(updated), session: "s3")
        XCTAssertEqual(reconnected.originFences, updated.originFences)
        XCTAssertNil(reconnected.foldedSequence)
        let sameTuples = v2Wire(session: "s3", authority: ["4243": origin(900, 3), "4242": origin(12, 3)], base: base)
        XCTAssertEqual(try applyV2(reconnected, sameTuples, now: 100.6).held?.expiresAt, 101.3)
        XCTAssertEqual(try applyV2(reconnected, v2Wire(session: "s3", authority: ["4243": origin(900, 2), "4242": origin(12, 3)], base: base), now: 100.6),
                       reconnected, "an older 4243 tuple is refused")
        XCTAssertEqual(try applyV2(reconnected, v2Wire(session: "s3", authority: ["4243": origin(900, 3), "4242": origin(12, 2)], base: base), now: 100.6),
                       reconnected, "an older 4242 tuple is refused")
        XCTAssertEqual(try applyV2(reconnected, sameTuples, now: 101.35), reconnected, "and the expired tuple stays expired")

        // Membership recovery after migration carries the fence as it is: pending, with its deadline.
        let away = BlendPreview.readerAfterMembership(updated, members: ["4242", "4244"])
        XCTAssertEqual(away.retiredMembers, [BlendPreviewReader.RetiredMember(row: "4243", fence: updated.originFences["4243"], floor: nil)])
        let returned = try opened(BlendPreview.readerAfterMembership(away, members: ["4242", "4243"]), session: "s4")
        XCTAssertEqual(returned.originFences["4243"], updated.originFences["4243"])
        let onReturn = v2Wire(session: "s4", authority: ["4243": origin(900, 3), "4242": origin(12, 3)], base: base)
        XCTAssertEqual(try applyV2(returned, onReturn, now: 100.9).held?.expiresAt, 101.3)
        XCTAssertEqual(try applyV2(returned, onReturn, now: 101.35), returned)

        // Before any frame is accepted the order stays, and every attempt reads
        // the current display: a reset before migration still retires the tuple.
        let resetFirst = try opened(BlendPreview.readerReset(newerV1), session: "s5")
        XCTAssertEqual(resetFirst.foldedSequence, BlendPreviewReader.FoldedSequence(epoch: 900, seq: 3, originEventId: 4243))
        XCTAssertEqual(try applyV2(resetFirst, v2Wire(session: "s5", authority: ["4243": origin(900, 3), "4242": origin(12, 2)], base: base), now: 100.4),
                       resetFirst, "a tuple on display before the reset is not replayed into v2")
        XCTAssertEqual(try applyV2(resetFirst, v2Wire(session: "s5", authority: ["4243": origin(900, 4), "4242": origin(12, 2)], base: base), now: 100.4)
                           .held?.expiresAt, 101.4)
    }

    /// lane1b's exact-delta review of d915700df1 (R1, G1, G2): a floor for a
    /// row the page no longer folds is that row's retired evidence. It merges
    /// by max with what the row already left — the boundary that retires the
    /// row never replaces a newer floor with one taken before the first
    /// membership — and each new row counts toward the coverage limit.
    func testANonMemberFloorMergesIntoRetiredEvidenceAndNeverRegresses() throws {
        func retiredFloor(_ reader: BlendPreviewReader, _ row: String) -> Int? {
            reader.retiredMembers.first { $0.row == row }?.floor
        }
        // G1: floor 10 before any membership; the first membership is not a
        // change, so it stays in `floors`. Floor 21 arrives while 4243 is out.
        var r = BlendPreview.readerAfterCommitFloor(.empty, FoldRevision(["4243": 10]))
        r = BlendPreview.readerAfterMembership(r, members: ["4242", "4244"])
        r = BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 21]))
        XCTAssertEqual(retiredFloor(r, "4243"), 21)
        r = BlendPreview.readerAfterMembership(r, members: ["4242", "4245"])
        XCTAssertEqual(retiredFloor(r, "4243"), 21, "the pre-membership floor 10 never overwrites the newer 21")
        r = BlendPreview.readerAfterMembership(r, members: ["4242", "4243"])
        XCTAssertEqual(r.floors?.rows["4243"], 21, "4243 returns with its newest floor")
        let base15: [String: Int] = ["4242": 10, "4243": 15]
        XCTAssertNil(read(r, try foldedFrame(origin: 4243, epoch: 1, seq: 1, baseRev: 15, base: base15), at: 100).held,
                     "a preview composed on 4243@15, below the committed 21, is refused")
        let base21: [String: Int] = ["4242": 10, "4243": 21]
        XCTAssertEqual(read(r, try foldedFrame(origin: 4243, epoch: 1, seq: 1, baseRev: 21, base: base21), at: 100).held?.p, 0.6,
                       "one covering 21 is admitted")

        // G2: a non-member floor max-merges; it never enters the fold's floors.
        var m = BlendPreview.readerAfterMembership(.empty, members: ["4242", "4243"])
        m = BlendPreview.readerAfterCommitFloor(m, FoldRevision(["4250": 5]))
        m = BlendPreview.readerAfterCommitFloor(m, FoldRevision(["4250": 3]))
        XCTAssertEqual(retiredFloor(m, "4250"), 5, "5 is kept over a later 3")
        XCTAssertNil(m.floors?.rows["4250"])
        // Eight distinct non-member rows is at capacity; a ninth saturates.
        for row in ["4251", "4252", "4253", "4254", "4255", "4256"] {
            m = BlendPreview.readerAfterCommitFloor(m, FoldRevision([row: 1]))
        }
        XCTAssertEqual(m.retiredMembers.count, BlendPreviewReader.maxRetiredMembers - 1)
        m = BlendPreview.readerAfterCommitFloor(m, FoldRevision(["4257": 1]))
        XCTAssertEqual(m.retiredMembers.count, BlendPreviewReader.maxRetiredMembers)
        XCTAssertEqual(m.evidenceSaturated, false, "at capacity is not past it")
        m = BlendPreview.readerAfterCommitFloor(m, FoldRevision(["4258": 1]))
        XCTAssertEqual(m.retiredMembers.count, BlendPreviewReader.maxRetiredMembers + 1, "kept, not forgotten")
        XCTAssertEqual(m.evidenceSaturated, true, "a ninth row saturates")
    }

    /// lane1b's exact-delta review of d915700df1 (G3): the legacy ledger holds
    /// at most `maxOrigins` distinct origins (f211). Past that a new origin is
    /// refused rather than any order forgotten; an origin already held still
    /// moves forward.
    func testTheLegacyLedgerRefusesANewOriginPastItsBoundAndKeepsServingHeldOnes() throws {
        func frame(_ origin: Int, seq: Int) throws -> BlendPreviewFrame {
            try foldedFrame(origin: origin, epoch: 1, seq: seq, baseRev: 20, base: ["4242": 10, String(origin): 20])
        }
        var r = BlendPreviewReader.empty
        for origin in 5000..<(5000 + BlendPreviewReader.maxOrigins) {
            r = read(r, try frame(origin, seq: 1), at: 100)
        }
        XCTAssertEqual(r.legacyOrders.count, BlendPreviewReader.maxOrigins)
        XCTAssertEqual(read(r, try frame(5000 + BlendPreviewReader.maxOrigins, seq: 1), at: 100.1), r,
                       "a new origin past the bound is refused")
        let held = read(r, try frame(5000, seq: 2), at: 100.1)
        XCTAssertEqual(held.legacyOrders["5000"], BlendPreviewReader.FoldedSequence(epoch: 1, seq: 2, originEventId: 5000),
                       "an origin already held is still admitted")
        XCTAssertEqual(held.held?.originEventId, 5000)
        XCTAssertEqual(held.held?.seq, 2)
    }

    // MARK: - v2 equivalents of the six f211 membership scenarios (Native 423, additive)
    //
    // Each case below replays one `testA…`/`…Origin…`/`…Collapsing…` scenario
    // above on the protocol the composed client speaks
    // (`preview_protocol=folded-v2`): per-origin `(epoch, seq)` authority
    // instead of the scalar epoch and the legacy order, a server composite
    // with `fold_seq` instead of one origin's frame, and a session the
    // membership boundary drops so the page reopens its stream. The originals
    // stay exactly as they are. Where v2 differs by protocol the assertion
    // pins the v2 form of the same guarantee and says so in its message:
    // - a same origin tuple re-sent at a higher `fold_seq` is admitted under
    //   its first-seen deadline (no new lease) where v1 refused the replay
    //   outright; a replay of the `fold_seq` itself is refused;
    // - a v2 withdrawal is the whole composite; the server recomposes around
    //   the row that is still pending, whose lease is untouched;
    // - a snapshot an uncovered commit floor withdraws is refused outright,
    //   so no fence advances, where v1 recorded the order and withheld the
    //   display;
    // - a membership change drops the session, so each case reopens one.

    /// v2 of `testAMembershipChangeRetiresTheRemovedRowsFloorWithoutForgettingIt`.
    func testV2AMembershipChangeRetiresTheRemovedRowsFloorWithoutForgettingIt() throws {
        var r = try adopt(opened(), ab)
        r = try applyV2(r, v2Wire(authority: ["4242": origin(100, 2), "4243": origin(2, 1)]), now: 100)
        XCTAssertEqual(r.held?.p, 0.65)
        r = BlendPreview.readerAfterCommitFloor(r, raw: #"{"event_id":4242,"floor":{"4242":10,"4243":21}}"#, eventId: id)
        XCTAssertNil(r.held, "a member committed past the composed base withdraws the composite")
        XCTAssertEqual(BlendPreview.membershipChanges(r, members: Set(ab.keys)), false)
        XCTAssertEqual(BlendPreview.membershipChanges(r, members: Set(ac.keys)), true)
        r = try adopt(r, ac)
        XCTAssertEqual(r.authorityMembers, ["4242", "4244"])
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4243" }?.floor, 21, "the removed row's floor is kept, not erased")
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4243" }?.fence,
                       BlendPreviewReader.OriginFence(epoch: 2, seq: 1, retired: false, deadline: 101), "and so is its fence")
        XCTAssertNil(r.foldSession, "the session is dropped: the page reopens its stream on the new fold")
        let newFold: [String: Any] = ["4242": origin(100, 3), "4244": origin(7, 1)]
        r = try applyV2(opened(r, session: "s2"), v2Wire(session: "s2", authority: newFold, base: ac), now: 101)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ac), now: 101), 0.65,
                       "the new fold is no longer withheld by a row it does not contain")
        XCTAssertEqual(r.held?.expiresAt, 102)
        // A snapshot still composed for the old membership never applies — on
        // the new session, nor on the old one.
        XCTAssertEqual(try applyV2(r, v2Wire(2, session: "s2", authority: ["4242": origin(100, 3), "4243": origin(2, 2)]), now: 101.1), r)
        XCTAssertEqual(try applyV2(r, v2Wire(2, session: "s1", authority: newFold, base: ac), now: 101.1), r)
        // A member's floor still withdraws; a non-member's no longer can.
        XCTAssertEqual(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 99])).held, r.held)
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4244": 31])).held)
        XCTAssertNil(BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4242": 11])).held)
    }

    /// v2 of `testAnotherOriginsEpochNeverFencesTheReplacementOrigin`. There
    /// is no scalar epoch to keep out of another row's domain: each origin's
    /// `(epoch, seq)` is its own fence. So the proof is that a removed
    /// origin's fence is retired evidence that never orders the replacement,
    /// and that two owning rows of one fold order independently inside the
    /// composite, whose lease is the earliest pending deadline.
    func testV2AnotherOriginsEpochNeverFencesTheReplacementOrigin() throws {
        var r = try adopt(opened(), ab)
        r = try applyV2(r, v2Wire(authority: ["4243": origin(900, 2)]), now: 100)
        XCTAssertEqual(r.held?.p, 0.65)
        XCTAssertNil(r.originFences["4242"], "another row's epoch is not the page row's fence")
        XCTAssertEqual(r.epoch, -1, "and v2 never writes the scalar epoch")
        r = try adopt(r, ac)
        XCTAssertNil(r.held, "the old fold's preview is withdrawn at the boundary")
        r = try applyV2(opened(r, session: "s2"), v2Wire(session: "s2", authority: ["4244": origin(12, 81)], base: ac), now: 100.2)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: ac), now: 100.2), 0.65)
        XCTAssertEqual(r.held?.expiresAt, 101.2)
        XCTAssertEqual(r.retiredMembers.first { $0.row == "4243" }?.fence.map { [$0.epoch, $0.seq] }, [900, 2],
                       "the removed origin's fence is retained")
        XCTAssertEqual(r.originFences["4244"], BlendPreviewReader.OriginFence(epoch: 12, seq: 81, retired: false, deadline: 101.2),
                       "the replacement origin's epoch 12 is its own fence; 900 never ordered it")
        // Ordering within the replacement origin is unchanged.
        let olderTuples: [[String: Any]] = [["4244": origin(12, 80)], ["4244": origin(11, 99)]]
        for stale in olderTuples {
            XCTAssertEqual(try applyV2(r, v2Wire(2, session: "s2", authority: stale, base: ac), now: 100.3), r)
        }
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: ["4244": origin(12, 81)], base: ac), now: 100.3), r,
                       "the same fold sequence is a replay")
        XCTAssertEqual(try applyV2(r, v2Wire(2, session: "s2", authority: ["4244": origin(12, 81)], base: ac), now: 100.3).held?.expiresAt, 101.2,
                       "the same tuple at a later fold sequence keeps its first-seen deadline: no new lease")
        let advanced = try applyV2(r, v2Wire(2, session: "s2", authority: ["4244": origin(12, 82)], base: ac), now: 100.3)
        XCTAssertEqual(advanced.originFences["4244"]?.seq, 82)
        XCTAssertEqual(advanced.held?.seq, 2)
        XCTAssertEqual(advanced.held?.expiresAt, 101.3)

        // Steady state: two owning rows of one fold order independently too.
        var both = try adopt(opened(), ab)
        both = try applyV2(both, v2Wire(authority: ["4243": origin(900, 2)]), now: 100)
        both = try applyV2(both, v2Wire(2, authority: ["4242": origin(3, 7), "4243": origin(900, 2)]), now: 100.1)
        XCTAssertEqual(both.sessionOrigins, ["4242", "4243"], "the page row joins at epoch 3 beside 4243's 900")
        XCTAssertEqual(both.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 3, seq: 7, retired: false, deadline: 101.1))
        XCTAssertEqual(both.held?.expiresAt, 101, "the composite's lease is the earliest pending deadline, not a renewal")
        XCTAssertEqual(try applyV2(both, v2Wire(3, authority: ["4242": origin(3, 6), "4243": origin(900, 2)]), now: 100.2), both)
        let ownHigh = try applyV2(adopt(opened(), ab), v2Wire(authority: ["4242": origin(900, 1)]), now: 100)
        let joined = try applyV2(ownHigh, v2Wire(2, authority: ["4242": origin(900, 1), "4243": origin(12, 1)]), now: 100.1)
        XCTAssertEqual(joined.originFences["4243"]?.epoch, 12, "nor does the page row's own epoch fence another row")
        XCTAssertEqual(joined.held?.p, 0.65)
        // Neither a lower seq nor a withdrawal of one row speaks for the other's.
        var shared = try adopt(opened(), ab)
        shared = try applyV2(shared, v2Wire(authority: ["4242": origin(5, 1)]), now: 100)
        shared = try applyV2(shared, v2Wire(2, authority: ["4242": origin(5, 1), "4243": origin(5, 9)]), now: 100.1)
        shared = try applyV2(shared, v2Wire(3, authority: ["4242": origin(5, 3), "4243": origin(5, 9)]), now: 100.2)
        XCTAssertEqual(shared.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 5, seq: 3, retired: false, deadline: 101.2),
                       "the page row's seq 3 is never compared with 4243's seq 9")
        XCTAssertEqual(shared.held?.seq, 3)
        let retired4243: [String: Any] = ["4242": origin(5, 3), "4243": origin(5, 9, state: "revoked")]
        let recomposed = try applyV2(shared, v2Wire(4, authority: retired4243), now: 100.3)
        XCTAssertEqual(recomposed.held?.p, 0.65, "4243's withdrawal recomposes around the page row")
        XCTAssertEqual(recomposed.held?.expiresAt, 101.2, "and does not touch its lease")
        XCTAssertEqual(recomposed.originFences["4243"]?.retired, true)
        XCTAssertEqual(recomposed.originFences["4242"], shared.originFences["4242"])
        let withdrawn = try applyV2(shared, v2Wire(4, kind: "revoke", authority: retired4243), now: 100.3)
        XCTAssertNil(withdrawn.held, "a v2 withdrawal is the whole composite")
        XCTAssertEqual(withdrawn.originFences["4242"], shared.originFences["4242"], "but it does not speak for the page row's lease")
        XCTAssertEqual(try applyV2(withdrawn, v2Wire(5, authority: retired4243), now: 100.4).held?.expiresAt, 101.2,
                       "which the recomposition resumes, unrenewed")
    }

    /// v2 of `testASingletonsAcceptedIdentityStillFencesTheFoldAfterAReset`.
    /// The singleton visit is legacy by nature (v2 is a fold protocol); its
    /// accepted identity is the page row's fence, which the v2 fold it later
    /// joins validates against. One protocol difference is pinned, not hidden:
    /// the v1 ledger consumes a revoke frame's own `seq` (3 here), while the
    /// fence a singleton revoke records is the revoked tuple itself (through
    /// 2) — so v2 admits (100, 3) as a newer identity where v1 refused it, as
    /// `testSingletonAuthorityOutlivesTheDisplayAndFencesTheFoldItJoins` pins.
    func testV2ASingletonsAcceptedIdentityStillFencesTheFoldAfterAReset() throws {
        let a = ["4242": 10]
        var r = try adopt(.empty, a)
        r = read(r, try singleton(epoch: 100, seq: 2), at: 100)
        XCTAssertEqual(r.held?.expiresAt, 101)
        XCTAssertEqual(r.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: false, deadline: 101),
                       "the identity is recorded at acceptance")
        r = BlendPreview.readerReset(r) // disconnect / resync
        r = try opened(adopt(r, ab), session: "s2")
        XCTAssertEqual(r.originFences["4242"]?.seq, 2, "and survives the reset into the fold")
        let olderIdentities: [[String: Any]] = [["4242": origin(100, 1), "4243": origin(2, 1)],
                                                ["4242": origin(99, 9), "4243": origin(2, 1)]]
        for stale in olderIdentities {
            XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: stale), now: 100.5), r, "an older identity gets no lease")
        }
        let same: [String: Any] = ["4242": origin(100, 2), "4243": origin(2, 1)]
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: same), now: 100.5).held?.expiresAt, 101,
                       "the same identity gets no new lease: its first-seen deadline caps the fold")
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: same), now: 101), r, "and past it the tuple stays expired")
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: ["4242": origin(100, 3), "4243": origin(2, 1)]), now: 100.5).held?.expiresAt, 101.5,
                       "a newer identity of the same ledger is admitted")
        // A revoked singleton identity stays revoked through the upgrade.
        var revoked = try adopt(.empty, a)
        revoked = read(revoked, try singleton(epoch: 100, seq: 2), at: 100)
        revoked = read(revoked, BlendPreviewFrame(eventId: id, p: nil, status: "live", kind: .revoke,
                                                  epoch: 100, seq: 3, throughSeq: 2), at: 100.1)
        XCTAssertNil(revoked.held)
        XCTAssertEqual(revoked.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 100, seq: 2, retired: true, deadline: 101))
        revoked = try opened(adopt(BlendPreview.readerReset(revoked), ab), session: "s2")
        XCTAssertEqual(try applyV2(revoked, v2Wire(session: "s2", authority: same), now: 100.2), revoked,
                       "the revoked tuple cannot become pending again")
        XCTAssertEqual(try applyV2(revoked, v2Wire(session: "s2", authority: ["4242": origin(100, 4), "4243": origin(2, 1)]), now: 100.2).held?.seq, 1)
        // Protocol difference, pinned: v1 refused (100, 3) because its ledger
        // consumed the revoke's own seq; the v2 fence holds the revoked tuple
        // (100, 2), so (100, 3) is a newer identity here.
        XCTAssertEqual(try applyV2(revoked, v2Wire(session: "s2", authority: ["4242": origin(100, 3), "4243": origin(2, 1)]), now: 100.2).held?.p, 0.65)
    }

    /// v2 of `testARowThatLeavesAndReturnsKeepsItsFenceAndFloor`.
    func testV2ARowThatLeavesAndReturnsKeepsItsFenceAndFloor() throws {
        var r = try adopt(opened(), ab)
        r = try applyV2(r, v2Wire(authority: ["4242": origin(5, 7)]), now: 100)
        r = try applyV2(r, v2Wire(2, authority: ["4242": origin(5, 7), "4243": origin(900, 5)]), now: 100.1)
        XCTAssertEqual(r.held?.expiresAt, 101, "the page row's first-seen deadline bounds the composite")
        r = BlendPreview.readerAfterCommitFloor(r, FoldRevision(["4243": 21]))
        XCTAssertNil(r.held, "4243 committed past the composed base")
        r = try adopt(r, ac) // e.g. a cached detail, then the fresh one, then cached again
        XCTAssertEqual(r.retiredMembers, [BlendPreviewReader.RetiredMember(
            row: "4243", fence: BlendPreviewReader.OriginFence(epoch: 900, seq: 5, retired: false, deadline: 101.1), floor: 21)])
        XCTAssertEqual(r.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 5, seq: 7, retired: false, deadline: 101),
                       "the surviving row keeps its identity and deadline")
        XCTAssertNil(r.floors, "the removed row's floor leaves the fold with it")
        let onAC = try applyV2(opened(r, session: "s2"), v2Wire(session: "s2", authority: ["4244": origin(12, 1)], base: ac), now: 100.2)
        XCTAssertEqual(onAC.held?.baseFoldRevision?.rows, ac)
        XCTAssertEqual(onAC.sessionOrigins, ["4244"])
        // The surviving row's order carries across the change: an older tuple
        // is refused; the same tuple gets no new lease (v1 refused the replay
        // outright; v2 re-admits it under the deadline it had before the
        // change); a newer one advances.
        XCTAssertEqual(try applyV2(onAC, v2Wire(2, session: "s2", authority: ["4242": origin(5, 6), "4244": origin(12, 1)], base: ac), now: 100.3), onAC)
        XCTAssertEqual(try applyV2(onAC, v2Wire(2, session: "s2", authority: ["4242": origin(5, 7), "4244": origin(12, 1)], base: ac), now: 100.3)
                           .held?.expiresAt, 101, "the surviving row's order carries across the change")
        XCTAssertEqual(try applyV2(onAC, v2Wire(2, session: "s2", authority: ["4242": origin(5, 7), "4244": origin(12, 1)], base: ac), now: 101), onAC,
                       "and its expired tuple stays expired")
        let advanced = try applyV2(onAC, v2Wire(2, session: "s2", authority: ["4242": origin(5, 8), "4244": origin(12, 1)], base: ac), now: 100.3)
        XCTAssertEqual(advanced.originFences["4242"]?.seq, 8)
        XCTAssertEqual(advanced.held?.expiresAt, 101.2, "bounded by 4244's own first-seen deadline")
        // The flap back: 4243 returns with its fence and floor; nothing is renewed.
        r = try adopt(onAC, ab)
        XCTAssertNil(r.held)
        XCTAssertEqual(r.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 900, seq: 5, retired: false, deadline: 101.1))
        XCTAssertEqual(r.floors?.rows, ["4243": 21])
        XCTAssertEqual(r.retiredMembers.map(\.row), ["4244"])
        r = try opened(r, session: "s3")
        let rebased = ["4242": 10, "4243": 21]
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s3", authority: ["4243": origin(900, 5)], base: rebased), now: 100.4).held?.expiresAt, 101.1,
                       "the returned row's old identity is not granted a new lease")
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s3", authority: ["4243": origin(900, 5)], base: rebased), now: 101.1), r)
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s3", authority: ["4243": origin(899, 50)], base: rebased), now: 100.4), r)
        let uncovered = try applyV2(r, v2Wire(session: "s3", authority: ["4243": origin(900, 6)]), now: 100.4)
        XCTAssertNil(uncovered.held, "nor is a newer one on a base its kept commit floor has passed")
        XCTAssertEqual(uncovered, r, "v2 refuses the uncovered snapshot outright: no fence advances")
        let covered = try applyV2(r, v2Wire(session: "s3", authority: ["4243": origin(900, 6)], base: rebased), now: 100.4)
        XCTAssertEqual(covered.originFences["4243"]?.seq, 6)
        XCTAssertEqual(covered.held?.seq, 1)
    }

    /// v2 of `testResetAndAnUnchangedMembershipRenewNothing`.
    func testV2ResetAndAnUnchangedMembershipRenewNothing() throws {
        var r = try adopt(opened(), ab)
        r = try applyV2(r, v2Wire(authority: ["4243": origin(5, 1)]), now: 100)
        XCTAssertEqual(r.held?.seq, 1)
        XCTAssertEqual(try adopt(r, ab), r, "an unchanged membership changes nothing: the preview, session and fences included")
        XCTAssertEqual(adopt(r, nil as FoldRevision?), r, "an absent fold makes no claim")
        XCTAssertEqual(BlendPreview.readerAfterMembership(r, members: []), r, "and neither does an empty one")
        let first = try adopt(applyV2(opened(), v2Wire(authority: ["4243": origin(5, 1)]), now: 100), ab)
        XCTAssertEqual(first.held?.seq, 1, "the first membership is recorded, not a change")
        XCTAssertEqual(first.foldSession, "s1")
        XCTAssertEqual(first.authorityMembers, ["4242", "4243"])
        r = try adopt(r, ac)
        r = BlendPreview.readerReset(r) // an ordinary reconnect after the change keeps every fence
        r = try opened(adopt(r, ab), session: "s2")
        XCTAssertEqual(r.originFences["4243"], BlendPreviewReader.OriginFence(epoch: 5, seq: 1, retired: false, deadline: 101))
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: ["4243": origin(5, 1)]), now: 200), r,
                       "the replayed identity is past its first-seen deadline: nothing is renewed")
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s1", authority: ["4243": origin(5, 2)]), now: 200), r, "the old session says nothing")
        XCTAssertEqual(try applyV2(r, v2Wire(session: "s2", authority: ["4243": origin(5, 2)]), now: 200).held?.expiresAt, 201)
    }

    /// v2 of `testAFoldCollapsingToThePagesRowContinuesOnItsOwnLedger`: the
    /// page row's own fence is what its singleton frames resume under.
    func testV2AFoldCollapsingToThePagesRowContinuesOnItsOwnLedger() throws {
        let a = ["4242": 10]
        var r = try adopt(opened(), ab)
        r = try applyV2(r, v2Wire(authority: ["4242": origin(7, 2)]), now: 100)
        r = try applyV2(r, v2Wire(2, authority: ["4242": origin(7, 2), "4243": origin(900, 1)]), now: 100.1)
        XCTAssertEqual(r.held?.expiresAt, 101)
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 3), at: 100.2), r, "a singleton never applies to a two-row page")
        r = try adopt(r, a)
        XCTAssertNil(r.held)
        XCTAssertNil(r.foldSession)
        XCTAssertEqual(r.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 7, seq: 2, retired: false, deadline: 101),
                       "the row's accepted identity is its own fence now")
        XCTAssertEqual(r.retiredMembers.map(\.row), ["4243"])
        for stale in [try singleton(epoch: 7, seq: 1), try singleton(epoch: 6, seq: 9)] {
            XCTAssertEqual(read(r, stale, at: 100.3), r, "the row's accepted identity still fences")
        }
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 2), at: 100.3).held?.expiresAt, 101,
                       "the same identity resumes under its first-seen deadline, not a new lease")
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 2), at: 101), r, "and stays expired past it")
        r = read(r, try singleton(epoch: 7, seq: 3), at: 100.3)
        XCTAssertEqual(BlendPreview.displayed(r.held, held: try detail(revision: a), now: 100.3), 0.7)
        XCTAssertEqual(r.originFences["4242"], BlendPreviewReader.OriginFence(epoch: 7, seq: 3, retired: false, deadline: 101.3))
        r = BlendPreview.readerReset(r) // reconnect: after folded authority a replay never renews
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 3), at: 100.4), r)
        XCTAssertEqual(read(r, try folded(origin: 4242, epoch: 7, seq: 4, base: ab), at: 100.4), r,
                       "an old fold's frame is refused on the collapsed page")
        let reopened = try opened(r, session: "s2")
        XCTAssertEqual(try applyV2(reopened, v2Wire(session: "s2", authority: ["4242": origin(7, 4), "4243": origin(900, 2)]), now: 100.4), reopened,
                       "so is a v2 snapshot of the fold the page no longer has")
        XCTAssertEqual(read(r, try singleton(epoch: 7, seq: 4), at: 100.4).held?.seq, 4)
    }

}
