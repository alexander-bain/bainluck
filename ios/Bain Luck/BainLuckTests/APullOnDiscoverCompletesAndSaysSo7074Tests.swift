import XCTest
@testable import Bain_Luck

/// #7074's pull arm: **a pull on Discover completes against a CHANGED response,
/// and the reader is told which way it ended.**
///
/// ═══ WHAT WAS INCONCLUSIVE, AND WHY ═══
///
/// Alex, physical phone, TestFlight 1.0 (15): *"Pull gesture briefly shows
/// activity with no apparent change."* The issue ruled that INCONCLUSIVE in as
/// many words — identical content is not failure, and a refresh returning the
/// same markets is a correct refresh — and asked for the thing that separates
/// the readings: *"Prove gesture→request→completion and useful stable position
/// on a controlled changed-response test; show a clear completed/error state."*
///
/// Three arms, and only one of them existed:
///
///   1. **gesture → closure.** `AReaderCanSwipeAndRefreshDiscoverTests`
///      `.testPullingDownRunsTheRefresh` has proved this since 2026-09-14, with
///      a quiet-window control against a counter that ticks on its own. Not
///      re-proved here.
///   2. **request → completion, against a response that CHANGED.** Nobody had
///      built it. Against the live API it is unbuildable: the server may serve
///      the same cards twice, which is correct, so a test asserting the rows
///      moved would red on a working app. It needs a controlled response, which
///      is what the `DiscoverFeedProviding` seam is for. That is the first half
///      of this file.
///   3. **a clear completed/error state.** Measured absent — see
///      `DiscoverPullRefreshNotice` for the read. That is the second half.
///
/// ═══ THE ARM THIS FILE DELIBERATELY DOES NOT CLAIM ═══
///
/// A changed-response test at this seam proves the MODEL completed and
/// republished. It cannot prove a finger did it, and it does not try: the
/// gesture lives one layer up and is already covered. Naming that boundary is
/// the point — the failure mode here would be a suite that reads like proof of
/// the whole chain while touching only its middle.
@MainActor
final class APullOnDiscoverCompletesAndSaysSo7074Tests: XCTestCase {

    // MARK: - Fakes

    private enum Reply { case ok(FeedResponse); case fail(Error) }

    /// Serves a scripted sequence and counts what it was asked for.
    ///
    /// The COUNT is load-bearing twice over: it proves the refresh issued a
    /// request at all (arm 2's first half), and it proves it issued exactly one
    /// — codex's "avoid duplicate loads" is a property of this number, and a
    /// refresh that fired two requests would still pass every assertion about
    /// the rows.
    private nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var count = 0

        init(_ script: [Reply]) { self.script = script }

        var callCount: Int { lock.withLock { count } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            await Task.yield()
            return try lock.withLock {
                count += 1
                guard !script.isEmpty else { throw URLError(.badServerResponse) }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    /// A page, optionally carrying the server's `edition` stamp.
    ///
    /// 🪤 **THE STAMP CHOOSES WHICH PUBLICATION BRANCH RUNS, AND A FIXTURE THAT
    /// OMITS IT SILENTLY PICKS ONE.** `DiscoverFeedReconcile.decision` returns
    /// `.reconcile` for any payload with no edition, so the obvious editionless
    /// fixture exercises the MERGE path and never touches `.repaint` — measured,
    /// by a mutant that disabled `.repaint` and survived a suite that looked like
    /// it was testing exactly that. Both paths are covered below, on purpose and
    /// by name; a survivor here would have been read as a weak test when what it
    /// actually said was "you are not on that branch".
    private func page(ids: [Int], hasMore: Bool = true, edition: String? = nil) throws -> FeedResponse {
        let stamp = edition.map { ",\"edition\":\"\($0)\"" } ?? ""
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":50,"offset":0,"has_more":\(hasMore)\(stamp)}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// The identity of what is on screen, as a reader would judge it: which
    /// markets, in which order. Not `items.count` — payload A and payload B here
    /// are the same LENGTH on purpose, so a test keyed on the count would pass
    /// on a refresh that republished A verbatim.
    private func shownMarkets(_ vm: DiscoverViewModel) -> [Int] {
        vm.items.compactMap { $0.futures?.id }
    }

    // MARK: - Arm 2: the controlled changed response

    /// Payload A, a pull, payload B — and the rows the reader sees are B's.
    ///
    /// The control that makes this mean something is that A and B have the same
    /// SHAPE (five futures cards, same limit, same `has_more`) and differ only in
    /// which markets they carry. Every cheap witness — a count, a "not empty", a
    /// `loading == false` — is satisfied by republishing A, which is precisely
    /// the state Alex could not distinguish from a working refresh.
    func testASecondLoadPublishesTheSecondPayloadAndNotTheFirst() async throws {
        let client = ScriptedClient([
            .ok(try page(ids: [1, 2, 3, 4, 5])),
            .ok(try page(ids: [6, 7, 8, 9, 10])),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)

        await vm.load()
        XCTAssertEqual(shownMarkets(vm), [1, 2, 3, 4, 5], "payload A did not reach the reader; nothing below this means anything")
        let versionAfterA = vm.itemsVersion

        await vm.load()

        XCTAssertEqual(
            shownMarkets(vm), [6, 7, 8, 9, 10],
            "the refresh completed and the reader is still looking at payload A. This is the state the "
            + "issue calls INCONCLUSIVE on a live server and which a controlled response makes decidable."
        )
        XCTAssertGreaterThan(
            vm.itemsVersion, versionAfterA,
            "`items` was never reassigned, so no dependent view body re-ran — the rows could be right in "
            + "the model and stale on the page."
        )
        XCTAssertEqual(client.callCount, 2, "the refresh must issue exactly one request of its own")
        XCTAssertNil(vm.error, "a successful refresh leaves no error behind for the next reader of this flag")
        XCTAssertFalse(vm.loading, "the refresh has not completed: `loading` is still true after `load()` returned")
    }

    /// The same claim on the OTHER publication branch.
    ///
    /// The test above rides `.reconcile`, because its payloads carry no edition
    /// stamp and an editionless response can never be `.repaint`. A server that
    /// stamps editions puts the identical reader gesture through
    /// `items = Self.interleave(renderable)` instead — a different line, a
    /// different failure, and one the test above cannot see at all.
    ///
    /// Both branches must land payload B, because which one runs is a property of
    /// the server's response and not of anything the reader did.
    func testTheRepaintBranchAlsoLandsTheSecondPayload() async throws {
        let client = ScriptedClient([
            .ok(try page(ids: [1, 2, 3, 4, 5], edition: "e1")),
            .ok(try page(ids: [6, 7, 8, 9, 10], edition: "e2")),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)

        await vm.load()
        XCTAssertEqual(shownMarkets(vm), [1, 2, 3, 4, 5], "payload A did not reach the reader on the stamped path")

        await vm.load()

        XCTAssertEqual(
            shownMarkets(vm), [6, 7, 8, 9, 10],
            "a new edition replaced nothing: the reader pulled, the server sent a different feed, and the "
            + "page kept the old one."
        )
        XCTAssertNil(vm.error)
    }

    /// The anti-vacuity control for the test above, and it is not ceremony.
    ///
    /// If `load()` republished whatever it was last given, the assertion above
    /// would pass on payload B alone and prove nothing about the refresh. Serving
    /// A TWICE must leave the rows unchanged — which is also the real case the
    /// issue protects ("identical content alone is not failure"): the same cards
    /// coming back is a correct refresh and must not read as one that failed.
    func testTheSameResponseTwiceIsACompletedRefreshAndNotAFailedOne() async throws {
        let client = ScriptedClient([
            .ok(try page(ids: [1, 2, 3, 4, 5])),
            .ok(try page(ids: [1, 2, 3, 4, 5])),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)

        await vm.load()
        await vm.load()

        XCTAssertEqual(shownMarkets(vm), [1, 2, 3, 4, 5], "the witness moves with the payload, not with the act of loading")
        XCTAssertNil(vm.error, "an unchanged feed is a successful refresh — the phase the reader is shown must be `.refreshed`")
        XCTAssertEqual(client.callCount, 2)
    }

    /// A failed refresh keeps the reader's feed and raises the error the notice
    /// is drawn from.
    ///
    /// Both halves matter and they pull against each other: yanking the cards
    /// away would destroy the reader's place while telling them something went
    /// wrong, and keeping the cards WITHOUT raising the flag is the silent
    /// failure #7074 is about.
    func testAFailedRefreshKeepsTheFeedAndRaisesTheErrorTheNoticeReads() async throws {
        let client = ScriptedClient([
            .ok(try page(ids: [1, 2, 3, 4, 5])),
            .fail(URLError(.notConnectedToInternet)),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)

        await vm.load()
        await vm.load()

        XCTAssertEqual(
            shownMarkets(vm), [1, 2, 3, 4, 5],
            "a failed refresh emptied the reader's feed. The cards they were reading are the only thing "
            + "they still have; a failure must cost them nothing but the update."
        )
        XCTAssertNotNil(
            vm.error,
            "the refresh failed and left `error` nil, so `refreshFeed` reads success and shows "
            + "'Checked just now' over a feed that was never refreshed."
        )
    }

    // MARK: - codex's constraint: the reset preserves what it must

    /// A refresh AGES the swipe store; it does not empty it (#5951), so the
    /// cards the reader has already rejected do not come back.
    ///
    /// Re-asserted here rather than taken on trust from #5951's suite: the pull
    /// arm's brief names "preserve account/swipe/history" as a condition of the
    /// repair, and a condition nobody states in the ship's own tests is a
    /// condition that silently stops holding.
    func testAPullDoesNotHandTheReaderBackTheCardsTheySwipedAway() {
        let now = Date().timeIntervalSince1970
        let store: [String: TimeInterval] = [
            "futures-101": now - 60,
            "futures-102": now - 3600,
            "futures-103": now - (13 * 86_400),
        ]

        let after = DiscoverView.dismissStoreAfterRefresh(store, now: now)

        XCTAssertEqual(
            Set(after.keys), Set(store.keys),
            "a pull emptied the swipe store, so every card the reader rejected this sitting is about to "
            + "be served back to them."
        )
        XCTAssertEqual(after, store, "the timestamps moved; an aged entry expires on a clock the reader never set")
    }

    /// And the ageing is real, not a pass-through — the anti-vacuity half of the
    /// test above. A helper that returned its input unchanged would satisfy it.
    func testTheSwipeStoreStillExpiresEntriesPastTheirWindow() {
        let now = Date().timeIntervalSince1970
        let store: [String: TimeInterval] = [
            "futures-201": now - 60,
            "futures-202": now - (30 * 86_400),
        ]

        let after = DiscoverView.dismissStoreAfterRefresh(store, now: now)

        XCTAssertEqual(Set(after.keys), ["futures-201"], "the refresh no longer prunes, so the store grows without bound")
    }

    // MARK: - Arm 3: the completed/error state, as a rule

    /// The two phases that speak, and what they say.
    func testTheNoticeSpeaksOnTheTwoOutcomesAndNowhereElse() {
        XCTAssertNil(
            DiscoverPullRefreshNotice.forPhase(.idle),
            "a notice on `.idle` is a permanent fixture at the top of the feed saying nothing happened"
        )
        XCTAssertNil(
            DiscoverPullRefreshNotice.forPhase(.refreshing),
            "`.refreshable` already draws a spinner under the reader's finger; a second in-flight marker "
            + "directly beneath it is two spinners for one request"
        )
        XCTAssertNotNil(
            DiscoverPullRefreshNotice.forPhase(.refreshed),
            "a completed pull says nothing, which is the defect: it renders identically to no pull"
        )
        XCTAssertNotNil(
            DiscoverPullRefreshNotice.forPhase(.failed),
            "a failed pull says nothing, which is the same defect wearing the worse outcome"
        )
    }

    /// Success and failure are distinguishable to a reader who is LOOKING and to
    /// one who is LISTENING.
    ///
    /// #1472's own lesson, one surface over: it is not enough that each phase
    /// produces some value; the values have to differ, and they have to differ in
    /// both channels. A `Button`'s accessibility label replaces its children, so
    /// two phases sharing a label are two phases that sound identical however
    /// different they look.
    func testTheTwoOutcomesAreTellableApartByEyeAndByEar() throws {
        let ok = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(.refreshed))
        let bad = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(.failed))

        XCTAssertNotEqual(ok.text, bad.text, "success and failure print the same line")
        XCTAssertNotEqual(ok.systemImage, bad.systemImage, "success and failure draw the same glyph")
        XCTAssertNotEqual(
            ok.accessibilityLabel, bad.accessibilityLabel,
            "success and failure announce identically, so a VoiceOver reader cannot tell a refreshed feed "
            + "from one that never refreshed"
        )
    }

    /// Only the failure carries the retry, and only the success clears itself.
    ///
    /// These two are the whole behavioural difference between the notices, and
    /// each is wrong in an obvious way if flipped: a success offering "try again"
    /// invites the reader to redo work that worked, and a failure that decays
    /// takes away the reader's only notice along with the control that answers it.
    func testOnlyFailureOffersTheRetryAndOnlySuccessClearsItself() throws {
        let ok = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(.refreshed))
        let bad = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(.failed))

        XCTAssertFalse(ok.offersRetry, "a refresh that worked is offering the reader a retry")
        XCTAssertTrue(bad.offersRetry, "the failure notice carries no way to answer it")
        XCTAssertTrue(ok.decays, "'Checked just now' will still be on screen ten minutes from now")
        XCTAssertFalse(
            bad.decays,
            "the failure notice clears itself, so the reader's only notice of the failure — and the retry "
            + "with it — disappears on a timer they did not start"
        )
    }

    /// One refresh, two places a reader may stand, ONE vocabulary.
    ///
    /// The notice does not get its own words for a state the end card already
    /// names (standing notice 35). Asserted against the footer's rule rather than
    /// against literals, so a copy change to either one cannot leave the two ends
    /// of the same scroll view describing the same event differently.
    func testTheNoticeSpeaksTheFootersWords() throws {
        for phase in [NativeFeedRefreshPhase.refreshed, .failed] {
            let notice = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(phase))
            let footer = NativeFeedEndCard.refreshPresentation(phase)
            XCTAssertEqual(
                notice.text, footer.status,
                "the top of the feed and the bottom of the feed describe \(phase) differently"
            )
            XCTAssertFalse(notice.text.isEmpty, "the borrowed line is empty, so the notice renders a blank row")
        }
    }

    /// No jargon reaches the reader (D102 / standing notice 34).
    func testTheNoticeSpeaksNoJargon() throws {
        let banned = [
            "refresh phase", "payload", "fetch", "request", "http", "api", "json", "cache",
            "nil", "error:", "timeout", "retry count", "bookmaker", "books",
        ]
        for phase in [NativeFeedRefreshPhase.refreshed, .failed] {
            let notice = try XCTUnwrap(DiscoverPullRefreshNotice.forPhase(phase))
            let spoken = (notice.text + " " + notice.accessibilityLabel).lowercased()
            for word in banned {
                XCTAssertFalse(
                    spoken.contains(word),
                    "\(phase) says '\(word)' to a reader: '\(notice.text)' / '\(notice.accessibilityLabel)'"
                )
            }
        }
    }

    // MARK: - The call site, read as source

    /// **THE ASSERTION THE RULE TESTS ABOVE CANNOT MAKE.**
    ///
    /// Every test in the section above passes with the notice never drawn. The
    /// rule is a value; the page is a `some View`, and a SwiftUI builder cannot be
    /// called from a test — the exact shape that let #4624's survivor and #7077's
    /// two photographed defects live under green rule suites. So the call site is
    /// read as text: the notice must be built from the LIVE phase and it must sit
    /// at the TOP of the feed, above the first card, which is the only place the
    /// reader who pulled is looking.
    func testDiscoverDrawsTheNoticeAtTheTopFromTheLivePhase() throws {
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        XCTAssertFalse(source.isEmpty, "DiscoverView.swift could not be read; this test proves nothing.")

        let call = try XCTUnwrap(
            source.range(of: "DiscoverPullRefreshNotice.forPhase("),
            "Discover never asks for the notice, so a pull renders exactly as it did before #7074 — "
            + "and every rule test in this file still passes."
        )
        let argument = source[call.upperBound...].prefix(60)
        XCTAssertTrue(
            argument.contains("footerRefreshPhase"),
            "the notice is built from something other than the live phase, so it is frozen on whatever it "
            + "was handed however right the rule is. Found:\n\(argument)"
        )

        let row = try XCTUnwrap(
            source.range(of: "DiscoverPullRefreshNoticeRow("),
            "the notice is computed and never rendered."
        )
        let anchor = try XCTUnwrap(
            source.range(of: ".id(Self.feedTopAnchor)"),
            "the top-of-feed anchor has moved; move this test with it."
        )
        XCTAssertTrue(
            anchor.upperBound < row.lowerBound,
            "the notice renders BEFORE the top anchor, so it is outside the feed's top."
        )

        // Above the first card, not merely above the anchor's file position.
        // `grouped` is computed immediately after the anchor and every card the
        // feed draws comes after it; a notice below that is a notice the reader
        // has to scroll to in order to learn that they no longer need to.
        let grouped = try XCTUnwrap(
            source.range(of: "let grouped = groupedItems"),
            "the grouped-feed computation has moved; move this test with it."
        )
        XCTAssertTrue(
            row.upperBound < grouped.lowerBound,
            "the notice renders below the card grid's own input, so it is not at the top of the feed."
        )
    }

    /// The retry control actually refreshes, and does NOT ask for the scroll
    /// return.
    ///
    /// The reader pressing it is already at the top — that is where the notice
    /// is — so `returningToTopWith:` would be a scroll to where they stand, the
    /// same no-op `.refreshable` is deliberately not given (#1472's
    /// `testPullToRefreshDoesNotAskForTheScrollReturn`).
    func testTheRetryRefreshesFromWhereTheReaderIsStanding() throws {
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        let row = try XCTUnwrap(source.range(of: "DiscoverPullRefreshNoticeRow("))
        let closure = source[row.upperBound...].prefix(160)

        XCTAssertTrue(
            closure.contains("refreshFeed()"),
            "the retry does not refresh, so the reader's only answer to a failure is inert. Found:\n\(closure)"
        )
        XCTAssertFalse(
            closure.contains("returningToTopWith"),
            "the retry asks for a scroll to the top from a control that is AT the top. Found:\n\(closure)"
        )
    }

    // MARK: - Reading source as source

    /// A file's text with comments and blank lines removed.
    ///
    /// Borrowed wholesale from `FooterRefreshSaysWhatItIsDoing1472Tests`, for the
    /// reason that suite records: it measured a scan matching the prose written
    /// to explain the code it was checking. Every scan above goes through here,
    /// so the long comment at this ship's own call site cannot satisfy its own
    /// test.
    private static func codeText(of relativePath: String) -> String {
        let source = (try? String(
            contentsOf: projectDirectory.appendingPathComponent(relativePath), encoding: .utf8
        )) ?? ""
        return source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { stripComment(String($0)) }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
            .joined(separator: "\n")
    }

    /// String-aware, and that is not fussiness: a naive `range(of: "//")` cuts
    /// every line holding a URL literal, and `DiscoverView` has them. The 1472
    /// suite pays for this too — same implementation, deliberately identical so
    /// the two scans of the same file cannot read different files.
    private static func stripComment(_ line: String) -> String {
        var inString = false
        var previous: Character? = nil
        let characters = Array(line)
        var index = 0
        while index < characters.count {
            let c = characters[index]
            if c == "\"" && previous != "\\" {
                inString.toggle()
            } else if !inString, c == "/", index + 1 < characters.count, characters[index + 1] == "/" {
                return String(characters[..<index])
            }
            previous = c
            index += 1
        }
        return line
    }

    /// The repo's `ios/Bain Luck` directory, from this file's own path.
    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
