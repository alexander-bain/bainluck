import XCTest
@testable import Bain_Luck

/// native/078, #4110 — a card the reader is looking at stops moving under them.
///
/// Alex, reading Discover in the app Tue 2026-09-08 3:30–3:42pm PT: *"the feed
/// re-rendered several times during load and a card he was reading disappeared."*
///
/// `DiscoverViewModel` had three writers that each assigned the WHOLE `items`
/// array through `FeedInterleave.byCategory`. The interleave is deterministic for
/// a given input, but the boot cache and the fresh network response are DIFFERENT
/// inputs, so they interleave to different orders — the boot paint was not a
/// prefix of the fresh paint. No race required; it is what a normal successful
/// load did.
///
/// These tests are the contract, not the plumbing. The four branches are pure
/// functions precisely so they can be stated as claims about behaviour rather
/// than as assertions about a view model's internals.
final class DiscoverFeedReconcileTests: XCTestCase {

    // MARK: - The four branches (discover/001's contract)

    /// Nothing painted ⇒ nothing to protect. Without this branch the common cold
    /// no-cache load would append every card in raw server order and lose the
    /// category interleave entirely — a regression dressed as a fix.
    func testAnEmptyListTakesTheFullInterleave() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 0, paintedEdition: nil, incomingEdition: "abc"),
            .repaint)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 0, paintedEdition: "abc", incomingEdition: "abc"),
            .repaint)
    }

    /// THE SHIP. Same edition ⇒ same cards in the same order ⇒ the reader's card
    /// keeps its slot. This is the branch that was missing.
    func testTheSameEditionMayNotReorderThePaintedList() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: "9f2c1ab740de55c3"),
            .reconcile)
    }

    func testADifferentEditionMayRepaint() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: "5c7ef69d20eff005"),
            .repaint)
    }

    /// Absent is a REAL branch, not a legacy shim: it covers an older backend and
    /// every empty refusal (`requires_auth`, `leader_unavailable`,
    /// `input_age_ceiling`), for which discover deliberately returns no token
    /// rather than a shared "empty edition" constant — so that three different
    /// failures are not reconciled as one agreed ordering.
    func testAnAbsentIncomingEditionReconcilesRatherThanReordering() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: nil),
            .reconcile)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: nil, incomingEdition: nil),
            .reconcile)
    }

    /// We painted a list whose ordering we cannot vouch for (a pre-`edition`
    /// cached body), and the server has now stated one. Defer to the one we can
    /// verify rather than pretending the two agree.
    func testAPaintedListWithNoEditionDefersToAServerThatHasOne() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: nil, incomingEdition: "abc"),
            .repaint)
    }

    // MARK: - The merge itself

    private func keys(_ items: [String]) -> [String] { items }

    func testAPaintedCardKeepsItsSlotAndTakesTheFreshContent() {
        // Same membership, server order totally different — which is exactly what
        // the interleave of a different input produces, and exactly what used to
        // be assigned over the top.
        let painted = ["a", "b", "c", "d"]
        let incoming = ["d", "c", "b", "a"]
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: painted, incoming: incoming, key: { $0 }),
            painted,
            "same cards ⇒ the reader's order survives, whatever order the server sent")
    }

    /// The incoming copy WINS on content and LOSES on position: a card keeps its
    /// slot but takes the fresh prices the 2-minute poll moved.
    func testTheIncomingCopyWinsOnContentAndLosesOnPosition() {
        struct Card: Equatable { let key: String; let price: Int }
        let painted = [Card(key: "a", price: 1), Card(key: "b", price: 1)]
        let incoming = [Card(key: "b", price: 99), Card(key: "a", price: 99)]
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: painted, incoming: incoming, key: \.key),
            [Card(key: "a", price: 99), Card(key: "b", price: 99)])
    }

    func testNewCardsArriveAtTheEndInTheServersOwnOrder() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(
                painted: ["a", "b"], incoming: ["x", "b", "y", "a", "z"], key: { $0 }),
            ["a", "b", "x", "y", "z"])
    }

    func testACardTheServerNoLongerSendsIsRemoved() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(
                painted: ["a", "b", "c"], incoming: ["a", "c"], key: { $0 }),
            ["a", "c"])
    }

    /// The property that matters to a reader, stated directly: for any painted
    /// list and any permutation of it, no surviving card changes its index.
    func testNoSurvivingCardEverChangesIndex() {
        let painted = (0..<40).map { "card-\($0)" }
        // A permutation with a third of the list dropped and five cards added.
        var incoming = painted.filter { !$0.hasSuffix("3") && !$0.hasSuffix("7") }.shuffled()
        incoming += ["new-1", "new-2", "new-3", "new-4", "new-5"]

        let merged = DiscoverFeedReconcile.merge(
            painted: painted, incoming: incoming, key: { $0 })
        let survivors = painted.filter(Set(incoming).contains)

        XCTAssertEqual(Array(merged.prefix(survivors.count)), survivors,
                       "survivors must appear in painted order, before anything new")
        XCTAssertEqual(Set(merged), Set(incoming), "membership is the server's")
        XCTAssertEqual(merged.count, Set(merged).count, "no duplicates")
    }

    func testMergingIntoAnEmptyPaintedListIsJustTheIncomingList() {
        // Guarded at the decision layer, but the merge must still be sane if it
        // is ever reached — a silent reorder here would be invisible.
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: [], incoming: ["a", "b"], key: { $0 }),
            ["a", "b"])
    }

    func testAnEmptyIncomingListRemovesEverything() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: ["a", "b"], incoming: [], key: { $0 }),
            [])
    }

    // MARK: - Decoding

    /// The token rides the response BODY, not a header, because it has to be
    /// readable out of the client's last-good body cache at boot — which is one
    /// of the three assignment sites this ship changes.
    func testTheEditionDecodesOffTheBody() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false,
         "edition": "5c7ef69d20eff005"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertEqual(response.edition, "5c7ef69d20eff005")
    }

    /// An older backend, and every empty refusal, carry no token at all. That has
    /// to decode to nil rather than throw — the absent branch is reached through
    /// this line.
    func testAPayloadWithNoEditionDecodesToNilRatherThanThrowing() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertNil(response.edition)
    }

    /// Tolerant like `cache`/`buildQuality`/`degradedReason` beside it: a
    /// malformed token degrades to ABSENT, never to a decode failure that would
    /// take the whole feed down over a string.
    func testAMalformedEditionDegradesToAbsentAndDoesNotKillTheFeed() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false,
         "edition": {"not": "a string"}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertNil(response.edition)
        XCTAssertEqual(response.limit, 50, "the rest of the payload still decoded")
    }
}
