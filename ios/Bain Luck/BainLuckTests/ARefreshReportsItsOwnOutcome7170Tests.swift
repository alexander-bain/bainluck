import XCTest
@testable import Bain_Luck

/// #7170 — **a refresh reports the outcome of its own request.**
///
/// 🔴 THE DEFECT. Pull down on Discover and the confirmation row said *"Feed
/// refreshed. Checked just now."* on a refresh that never republished the feed.
/// `DiscoverView.refreshFeed` inferred its outcome from `vm.error == nil` after
/// the await, and `load()` has NINE terminals that publish nothing AND set no
/// error. On an already-healthy feed `error` was already nil, so every one of them
/// read as success.
///
/// Measured on the disposable simulator against the live API, with an inert
/// control (`-launch_changed_refresh 0`) producing an identical result: the app
/// affirmed a refresh that did not happen. Strictly worse than saying nothing —
/// build 15 said nothing, so a reader could suspect.
///
/// 🧭 TWO INDEPENDENT ASSERTIONS, AND THE SPLIT IS THE DESIGN. The contract below
/// is "does the load tell the truth about itself"; the journey
/// (`AReaderCanSwipeAndRefreshDiscoverTests.testAPullRepublishesTheFeedAndSaysWhatItDid`)
/// is "does a finger produce a publication". Each can pass while the other fails,
/// and on the build that filed this issue the first one was the lie. A contract
/// test alone would have been satisfied by a load that honestly reported
/// `cancelled` forever.
///
/// The cases here are the ones a refresh can actually reach, terminal by terminal,
/// because a contract with an untested terminal is where the next silent exit
/// lives.
@MainActor
final class ARefreshReportsItsOwnOutcome7170Tests: XCTestCase {

    // MARK: - Fakes

    private enum Reply { case ok(FeedResponse); case fail(Error) }

    private nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var served = 0

        init(_ script: [Reply]) { self.script = script }
        var callCount: Int { lock.withLock { served } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            await Task.yield()
            return try lock.withLock {
                served += 1
                guard !script.isEmpty else { throw URLError(.badServerResponse) }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
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

    /// `extra` carries the response-level keys a given terminal needs (edition,
    /// cache status, build quality) so each test states its own precondition in
    /// one place rather than through four near-identical builders.
    private func response(
        ids: [Int], hasMore: Bool = true, limit: Int = 50, extra: String = ""
    ) throws -> FeedResponse {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":\(limit),"offset":0,"has_more":\(hasMore)\(extra)}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func cached(_ ids: [Int], edition: String? = nil) throws -> CachedDiscoverFeed {
        let extra = edition.map { ",\"edition\":\"\($0)\"" } ?? ""
        return CachedDiscoverFeed(
            response: try response(ids: ids, limit: 200, extra: extra),
            storedAt: ISO8601DateFormatter().date(from: "2026-09-19T12:00:00Z")!,
            ttlSeconds: 5,
            identity: "anon:s1"
        )
    }

    private func ids(of vm: DiscoverViewModel) -> [Int] {
        vm.items.compactMap { $0.futures?.id }
    }

    // MARK: - published: the one terminal that may say "refreshed"

    func testAPublishingLoadReportsPublished() async throws {
        let fake = ScriptedClient([.ok(try response(ids: Array(1...12)))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        let outcome = await vm.load()

        XCTAssertEqual(outcome, .published)
        XCTAssertEqual(vm.items.count, 12, "the terminal that reports published is the one that assigned items")
    }

    /// Codex's explicit carve-out, and it is a rule about the WORLD, not about us:
    /// *"A valid response with unchanged content may correctly report checked; card
    /// differences are not a universal success requirement."*
    ///
    /// The market genuinely may not have moved between two pulls. A contract that
    /// demanded difference would report a failure every quiet minute, which is the
    /// #7170 lie inverted — and it would make the app's honesty depend on the news.
    func testALoadServingIdenticalCardsStillReportsPublished() async throws {
        let sameCards = Array(1...12)
        let fake = ScriptedClient([
            .ok(try response(ids: sameCards)),
            .ok(try response(ids: sameCards)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        let first = await vm.load()
        let second = await vm.load()

        XCTAssertEqual(first, .published)
        XCTAssertEqual(
            second, .published,
            "A second load carrying the SAME cards reported \(second). Identical content is a correct, "
            + "completed refresh — the reader asked whether we checked, not whether the world moved."
        )
        XCTAssertEqual(ids(of: vm), sameCards)
    }

    /// Both publication paths, because only one of them is the obvious one.
    ///
    /// `.repaint` reassigns wholesale; `.reconcile` merges into the painted order
    /// (#4110, so a card the reader is mid-way through cannot move). Both ASSIGN
    /// `items`, so both are publications — and a contract that only recognised
    /// `.repaint` would report `cancelled`/`failed` on every ordinary same-edition
    /// revalidation, which is the overwhelmingly common case.
    func testBothReconcileAndRepaintPathsReportPublished() async throws {
        // RECONCILE: the painted edition and the incoming edition agree.
        let reconcileClient = ScriptedClient([
            .ok(try response(ids: Array(1...6), extra: ",\"edition\":\"e-1\""))
        ])
        let reconcileVM = DiscoverViewModel(
            client: reconcileClient,
            lastGood: FakeLastGood(try cached(Array(1...6), edition: "e-1")),
            telemetry: nil)
        let reconciled = await reconcileVM.load()

        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 6, paintedEdition: "e-1", incomingEdition: "e-1"),
            .reconcile,
            "fixture drifted: this case is meant to exercise the merge path")
        XCTAssertEqual(reconciled, .published, "a reconcile assigns items, so it published")

        // REPAINT: the server states a DIFFERENT ordering, so the list is rebuilt.
        let repaintClient = ScriptedClient([
            .ok(try response(ids: Array(20...27), extra: ",\"edition\":\"e-2\""))
        ])
        let repaintVM = DiscoverViewModel(
            client: repaintClient,
            lastGood: FakeLastGood(try cached(Array(1...6), edition: "e-1")),
            telemetry: nil)
        let repainted = await repaintVM.load()

        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 6, paintedEdition: "e-1", incomingEdition: "e-2"),
            .repaint,
            "fixture drifted: this case is meant to exercise the repaint path")
        XCTAssertEqual(repainted, .published, "a repaint assigns items, so it published")
        XCTAssertEqual(ids(of: repaintVM), Array(20...27))
    }

    // MARK: - cancelled: THE terminal the live defect actually reached

    /// 🔴 THE MEASURED ONE. #7170 reasoned its way to a superseded generation; the
    /// build says otherwise. With `OUTCOME` drawn in the rig badge, a real pull on
    /// `D2DA47A0` read **`OUTCOME cancelled · FEED 1 → 1 · PULLS 0 → 1`** — the
    /// gesture landed, the load ended at the cancellation terminal, nothing
    /// published. There was no competing load at all.
    ///
    /// This is why the fix could not have been "a better generation guard": the
    /// hypothesis in the issue was wrong, and only a witness that names the
    /// terminal could show it. Cancellation must stay quiet to the SCREEN (no error
    /// banner, content kept — L2-214 Item 2) while being loud to the CALLER.
    func testACancelledLoadReportsCancelledAndSetsNoError() async throws {
        let fake = ScriptedClient([.fail(CancellationError())])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        let outcome = await vm.load()

        XCTAssertEqual(outcome, .cancelled)
        XCTAssertNil(
            vm.error,
            "A cancellation must not draw an error banner — and THAT is exactly why the caller cannot "
            + "read `error == nil` as success. Both halves of this assertion are the bug."
        )
        XCTAssertFalse(vm.loading)
    }

    /// The defect in one assertion, at the seam where it was committed.
    ///
    /// A healthy feed, then a cancelled refresh: `error` is nil BEFORE and nil
    /// AFTER, so the signal `refreshFeed` used to read is byte-identical between a
    /// successful refresh and one that did nothing. The outcome is what separates
    /// them, and without it no amount of care at the call site could have.
    func testACancelledRefreshIsIndistinguishableFromSuccessByErrorAlone() async throws {
        let fake = ScriptedClient([
            .ok(try response(ids: Array(1...12))),
            .fail(CancellationError()),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        let firstOutcome = await vm.load()
        XCTAssertEqual(firstOutcome, .published)
        let errorAfterSuccess = vm.error
        let versionAfterSuccess = vm.itemsVersion

        let secondOutcome = await vm.load()

        XCTAssertNil(errorAfterSuccess)
        XCTAssertNil(vm.error)
        XCTAssertEqual(
            vm.itemsVersion, versionAfterSuccess,
            "the cancelled refresh published nothing, so the feed version did not move")
        XCTAssertEqual(secondOutcome, .cancelled)
        XCTAssertNotEqual(
            firstOutcome, secondOutcome,
            "`error` was nil after BOTH loads and only one of them refreshed anything. Any caller "
            + "deriving its message from `error` announces 'Feed refreshed. Checked just now.' over "
            + "the second one — which is #7170, verbatim."
        )
        XCTAssertEqual(
            DiscoverView.refreshPhase(for: firstOutcome), .refreshed)
        XCTAssertEqual(
            DiscoverView.refreshPhase(for: secondOutcome), .idle,
            "and the phase rule must not hand the cancelled one the success row")
    }

    // MARK: - failed: honest failures, with and without content to keep

    /// Codex's "failure with retained content": the reader's cards stay, the banner
    /// tells the truth, and the outcome is `failed` rather than the silence that
    /// would leave a stale "refreshing" state on the footer.
    func testAFailedRefreshKeepingCachedContentReportsFailed() async throws {
        let fake = ScriptedClient([.fail(URLError(.notConnectedToInternet))])
        let vm = DiscoverViewModel(
            client: fake,
            lastGood: FakeLastGood(try cached(Array(1...9))),
            telemetry: nil,
            retryBudget: 0.1)

        let outcome = await vm.load()

        XCTAssertEqual(outcome, .failed)
        XCTAssertEqual(ids(of: vm), Array(1...9), "the reader's content was kept, not blanked")
        XCTAssertEqual(vm.error, "Showing recent markets — couldn't refresh")
        XCTAssertTrue(vm.refreshFailedShowingCache)
    }

    func testAFailedLoadWithNothingToKeepReportsFailed() async throws {
        let fake = ScriptedClient([.fail(URLError(.notConnectedToInternet))])
        let vm = DiscoverViewModel(
            client: fake, lastGood: nil, telemetry: nil, retryBudget: 0.1)

        let outcome = await vm.load()

        XCTAssertEqual(outcome, .failed)
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(vm.error, "Couldn't load feed")
    }

    /// Codex named `unavailable` beside cancellation and supersession, and it is
    /// the one of the three that was ALREADY honest — `mayReplaceRendered` refuses
    /// the typed-UNAVAILABLE body and sets an error (L2-238). Pinned anyway,
    /// because "it happens to set an error today" is how the other terminals were
    /// justified too, and this asserts the outcome rather than the side effect.
    ///
    /// It is also the case a reader hits by pulling twice quickly: the backend
    /// answers the immediate second request out of its singleflight with this.
    func testAnUnavailableResponseOverRenderedContentReportsFailed() async throws {
        let fake = ScriptedClient([
            .ok(try response(ids: Array(1...12))),
            .ok(try response(ids: [], hasMore: false, extra: ",\"cache\":{\"status\":\"unavailable\"}")),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        let seed = await vm.load()
        XCTAssertEqual(seed, .published)
        let outcome = await vm.load()

        XCTAssertEqual(
            outcome, .failed,
            "A typed-UNAVAILABLE body knows nothing about the feed. It is refused, and the refusal is "
            + "reported — never as an empty feed and never as a completed refresh."
        )
        XCTAssertEqual(ids(of: vm), Array(1...12), "the rendered generation was not blanked")
        XCTAssertEqual(vm.error, "Showing recent markets — couldn't refresh")
    }

    // MARK: - the phase rule the reader actually sees

    /// The whole mapping, in one place, including the two that must say NOTHING.
    ///
    /// Hoisted out of the view for this (`DiscoverView.refreshPhase(for:)`): the
    /// decision used to live inside an `async` method on a `View`, where no unit
    /// test could reach it and a test could only restate it.
    func testOnlyAPublishedLoadMayTellTheReaderItRefreshed() {
        XCTAssertEqual(DiscoverView.refreshPhase(for: .published), .refreshed)
        XCTAssertEqual(DiscoverView.refreshPhase(for: .failed), .failed)

        for silent: DiscoverLoadOutcome in [.superseded, .cancelled] {
            let phase = DiscoverView.refreshPhase(for: silent)
            XCTAssertNotEqual(
                phase, .refreshed,
                "\(silent) published nothing and was given the success row — this is #7170 itself."
            )
            XCTAssertEqual(
                phase, .idle,
                "\(silent) got \(phase). A refresh that cannot speak for the screen withdraws: "
                + "`.failed` would be the mirror lie, stranding a 'couldn't refresh' banner over "
                + "content a newer load is about to replace."
            )
        }
    }

    // MARK: - the call site, read as source

    /// 🔴 THE TWO MUTANTS NOTHING ABOVE CAN KILL, AND WHY THEY ARE SCANNED.
    ///
    /// Both halves of this ship live inside `refreshFeed` — an `async` method on a
    /// `View`. Every assertion above could pass with the call site reverted:
    ///   * revert the phase line to `if vm.error == nil` and the contract still
    ///     reports honestly, `refreshPhase(for:)` is still perfect, and nothing
    ///     reads it. That is #7170 restored, with a full green suite.
    ///   * revert the unstructured `Task` and the pull is cancelled again — the
    ///     unit suite cannot see it, because a fake client is never cancelled by a
    ///     SwiftUI gesture teardown.
    ///
    /// The journey covers the second and NOT the first (it asserts publication, not
    /// which sentence the notice chose), so neither is covered twice and this is not
    /// ceremony. Scanned through `codeText`, which strips comments — the long note
    /// at the call site cannot satisfy its own test.
    /// 🪤 SCOPED TO `refreshFeed`'S BODY, AND THE FIRST DRAFT WAS NOT — it scanned
    /// the whole file for `vm.error == nil` and went red on this ship's own green
    /// build. The hit was `onChange(of: vm.loading)`, reporting a screen-timing
    /// outcome, which is a correct and unrelated use of the same expression. A
    /// file-wide ban would have been a guard aimed at a string rather than at the
    /// decision, and the next legitimate use would have paid for it.
    func testRefreshFeedTakesItsPhaseFromTheLoadOutcomeAndNotFromTheErrorString() throws {
        let body = try Self.bodyOfRefreshFeed()

        XCTAssertTrue(
            body.contains("footerRefreshPhase = Self.refreshPhase(for: outcome)"),
            "refreshFeed no longer sets its phase from the load's outcome. The rule in "
            + "`refreshPhase(for:)` can be flawless and unread — which is #7170 exactly: the notice was "
            + "never wrong about the phase it was given, it was given the wrong phase."
        )
        XCTAssertFalse(
            body.contains("vm.error"),
            "refreshFeed is reading the model's error string to decide what to tell the reader. `load()` "
            + "has nine terminals that publish nothing and set no error, so on an already-healthy feed "
            + "that reads every one of them as 'Feed refreshed. Checked just now.'\n\(body)"
        )
    }

    /// The line that makes a pull publish, pinned as text for the reason above.
    ///
    /// MEASURED, not reasoned: with a structured `await vm.load()` here, a real
    /// pull on `D2DA47A0` read `OUTCOME cancelled · FEED 1 → 1 · PULLS 0 → 1`.
    /// `.refreshable`'s task is torn down while the reader is still on Discover and
    /// takes the request with it. An unstructured `Task` does not inherit that
    /// cancellation; `.value` is still awaited, so the spinner behaves as before.
    func testTheRefreshLoadDoesNotInheritTheGesturesCancellation() throws {
        let body = try Self.bodyOfRefreshFeed()

        XCTAssertTrue(
            body.contains("let outcome = await Task { @MainActor in await vm.load() }.value"),
            "the refresh load is a structured child of the gesture's task again, so `.refreshable` "
            + "tearing down cancels the reader's request and the pull publishes nothing (#7170)."
        )
    }

    // MARK: - the rig witness itself

    /// The badge field that produced the diagnosis has to be parseable, and its
    /// vocabulary must not contain the separator the parser splits on — a word
    /// carrying `·` would silently split one field into two and the journey would
    /// read a neighbouring value as the outcome.
    func testEveryOutcomeHasADistinctSeparatorSafeBadgeWord() {
        let all: [DiscoverLoadOutcome?] = [nil, .published, .failed, .superseded, .cancelled]
        let words = all.map { DiscoverView.rigOutcomeWord($0) }

        XCTAssertEqual(Set(words).count, all.count, "two terminals share a badge word: \(words)")
        for word in words {
            XCTAssertFalse(word.isEmpty, "an empty field reads to the parser like a build without it")
            XCTAssertFalse(
                word.contains("\u{00B7}"),
                "'\(word)' contains the badge separator, so it would split into two fields")
            XCTAssertFalse(word.contains(" "), "'\(word)' has a space; fields are parsed as `NAME value`")
        }
        XCTAssertEqual(
            DiscoverView.rigOutcomeWord(nil), "none",
            "before the first refresh the field must be PRESENT and say nothing happened")
    }

    // MARK: - reading the call site

    /// Just `refreshFeed`'s own body, comments already stripped.
    ///
    /// Sliced to the method rather than the file because both scans here are about
    /// ONE decision, and the same expressions are legitimate elsewhere in a
    /// 3,300-line view. The end is the first `}` at method indentation: nested
    /// closures are deeper, so this cannot run past the method it was asked for —
    /// and if the signature ever moves, the unwrap fails loudly instead of
    /// scanning an empty string and passing.
    private static func bodyOfRefreshFeed(
        file: StaticString = #filePath, line: UInt = #line
    ) throws -> String {
        let source = codeText(of: "Bain Luck/Views/DiscoverView.swift")
        XCTAssertFalse(source.isEmpty, "DiscoverView.swift could not be read; this proves nothing.",
                       file: file, line: line)

        let signature = try XCTUnwrap(
            source.range(of: "private func refreshFeed(returningToTopWith"),
            "refreshFeed's signature has changed; move this scan with it.",
            file: file, line: line
        )
        let rest = source[signature.upperBound...]
        let end = try XCTUnwrap(
            rest.range(of: "\n    }"),
            "could not find the end of refreshFeed; the scan would otherwise read the rest of the file.",
            file: file, line: line
        )
        return String(rest[..<end.lowerBound])
    }

    /// Borrowed from `APullOnDiscoverCompletesAndSaysSo7074Tests`, deliberately
    /// byte-identical: two scans of the same file must not read different files.
    /// Comments are stripped, so prose explaining the code cannot satisfy a scan of
    /// it — that suite measured exactly that failure.
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

    /// String-aware: a naive `range(of: "//")` cuts every line holding a URL
    /// literal, and `DiscoverView` has them.
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
