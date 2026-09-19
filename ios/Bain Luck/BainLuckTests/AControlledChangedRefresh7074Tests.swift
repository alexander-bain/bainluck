import XCTest
@testable import Bain_Luck

/// #7074 — the rule behind the rig affordance that lets a journey with a REAL
/// FINGER perform a controlled changed-response experiment.
///
/// 🔴 THE ARM. Alex, physical phone, build 15: *"Pull gesture briefly shows
/// activity with no apparent change."* The issue ruled it INCONCLUSIVE and named
/// the bar: *"Prove gesture→request→completion and useful stable position on a
/// controlled changed-response test"* — then, one line down, *"Test actual
/// gestures and read frames, not state-machine tests alone."*
///
/// Against the live API those two sentences cannot both be satisfied: production
/// may legitimately serve the same cards twice, so a finger-driven journey
/// asserting "the cards changed" reds on a working app. native/243 took the
/// controlled half onto the `DiscoverFeedProviding` seam and said out loud what
/// that costs — the rule is proven and nothing is proven about whether a gesture
/// produces it. `LaunchRig.changedRefreshKey` closes the other half by keeping
/// the real network, the real gesture and the real screen, and making the
/// DIFFERENCE the controlled variable.
///
/// This file is the rule; `AReaderCanSwipeAndRefreshDiscoverTests` is the finger.
/// Neither is sufficient and the split is the point: a pure suite cannot reach a
/// SwiftUI builder returning an opaque type, and a journey cannot enumerate the
/// refusals below.
final class AControlledChangedRefresh7074Tests: XCTestCase {

    private typealias VM = DiscoverViewModel

    private let painted = ["a", "b", "c", "d", "e"]

    // MARK: - The reader's path, which is every path but one

    /// THE ASSERTION THAT MAKES THIS AN AFFORDANCE RATHER THAN A DEFECT. No
    /// launch argument, no change — not "a smaller change", none. Everything
    /// else in this file describes behaviour nobody shipping ever reaches.
    func testNoDropAskedForLeavesThePayloadExactlyAsTheServerSentIt() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPublishedNetworkFeed: true, drop: nil)

        XCTAssertEqual(staged.items, painted)
        XCTAssertEqual(
            staged.edition, "ed-1",
            "the edition must survive untouched too: a restamped token would send a reader's "
            + "ordinary refresh down the repaint branch and move cards under their thumb — #4110, "
            + "the exact defect DiscoverFeedReconcile exists to prevent"
        )
    }

    /// Release has no call site at all (`#if DEBUG`), so this is what the
    /// function must do if it is ever reached with a nil drop.
    func testNoDropIsInertEvenOnAnEmptyOrEditionlessPayload() {
        let empty = VM.rigStagedRefresh(
            items: [String](), edition: nil, hasPublishedNetworkFeed: true, drop: nil)
        XCTAssertTrue(empty.items.isEmpty)
        XCTAssertNil(empty.edition)
    }

    // MARK: - The controlled change itself

    func testAStagedRefreshWithholdsTheFirstCardsSoTheTopOfTheFEEDCHANGES() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPublishedNetworkFeed: true, drop: 2)

        XCTAssertEqual(staged.items, ["c", "d", "e"])
        XCTAssertNotEqual(
            staged.items.first, painted.first,
            "the whole experiment is that the card at the top is not the card that was there; "
            + "a change the reader cannot see is the state Alex already reported"
        )
    }

    /// The restamp is not cosmetic. `DiscoverFeedReconcile` is entitled to assume
    /// the server's token moves when ordered membership moves, so handing back
    /// the original token after withholding cards would assert the opposite of
    /// what the rig just did — and the list would take `.reconcile`, the branch a
    /// changed response does NOT take. The journey would then be testing the
    /// wrong branch while looking green.
    func testWithholdingCardsRestampsTheEditionSoTheCHANGEDBranchIsTheOneTaken() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPublishedNetworkFeed: true, drop: 2)

        XCTAssertNotEqual(staged.edition, "ed-1")
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: painted.count,
                paintedEdition: "ed-1",
                incomingEdition: staged.edition),
            .repaint,
            "a genuinely different list must reach the reader through the repaint branch"
        )
    }

    /// An absent edition is a real state (an older backend, every empty refusal),
    /// and `decision` returns `.reconcile` for ANY editionless payload regardless
    /// of what it contains. So a rig that withheld cards and left the token nil
    /// would stage a changed list that could never take the changed branch.
    ///
    /// 🪤 This is native/243's survivor, one layer up: that session's mutant
    /// "a refresh republishes what it already had" survived because its fixture
    /// had no edition and therefore could not reach `.repaint` at all. A survivor
    /// can mean UNREACHABLE rather than weak, and the same trap is live here.
    func testAnEditionlessPayloadIsStillRestampedIntoTheCHANGEDBranch() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: nil, hasPublishedNetworkFeed: true, drop: 2)

        XCTAssertNotNil(
            staged.edition,
            "left nil, this list reconciles in place and the journey silently tests the branch "
            + "that runs when NOTHING changed"
        )
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: painted.count, paintedEdition: nil, incomingEdition: staged.edition),
            .repaint
        )
    }

    // MARK: - The three refusals, each a state the journey must not misread

    /// The first network publication is payload A — the thing the change is
    /// measured AGAINST. Shortening it too would leave the journey comparing two
    /// shortened lists and reporting the difference between them as the
    /// experiment's result.
    ///
    /// This rule was always right; what was wrong was the witness the CALL SITE
    /// handed it (`!items.isEmpty`, which a cache seed satisfies). The container
    /// tests below are the ones that can see that, and they are why this file now
    /// builds view models instead of only calling a pure function.
    func testTheFirstNetworkPublicationIsNeverShortened() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPublishedNetworkFeed: false, drop: 2)

        XCTAssertEqual(staged.items, painted)
        XCTAssertEqual(staged.edition, "ed-1")
    }

    /// An empty payload is not a smaller payload. It is `mayReplaceRendered`'s
    /// refusal terminal and Discover's empty state, so a rig that emptied the
    /// feed would manufacture a different defect and the journey would
    /// photograph that instead of the one it came for.
    func testADropThatWouldEmptyTheFeedKeepsACardOnScreen() {
        for oversized in [painted.count, painted.count + 1, 500] {
            let staged = VM.rigStagedRefresh(
                items: painted, edition: "ed-1", hasPublishedNetworkFeed: true, drop: oversized)

            XCTAssertFalse(
                staged.items.isEmpty,
                "drop \(oversized) emptied a \(painted.count)-card feed, which is the empty-state "
                + "terminal rather than a changed response"
            )
            XCTAssertEqual(staged.items, ["e"], "the survivor is the LAST card, not an arbitrary one")
        }
    }

    /// A one-card feed has no card it can withhold without emptying itself, so
    /// the honest answer is the unchanged payload — not a staged "change" that
    /// changed nothing, which the journey would read as a completed experiment.
    func testASingleCardFeedIsLeftAloneRatherThanStagedIntoANonChange() {
        let staged = VM.rigStagedRefresh(
            items: ["only"], edition: "ed-1", hasPublishedNetworkFeed: true, drop: 3)

        XCTAssertEqual(staged.items, ["only"])
        XCTAssertEqual(
            staged.edition, "ed-1",
            "an unchanged list must keep its unchanged token, or the reader takes a wholesale "
            + "repaint to arrive at exactly the cards they already had"
        )
    }

    func testAnEmptyPayloadIsLeftAloneRatherThanRestamped() {
        let staged = VM.rigStagedRefresh(
            items: [String](), edition: "ed-1", hasPublishedNetworkFeed: true, drop: 2)

        XCTAssertTrue(staged.items.isEmpty)
        XCTAssertEqual(staged.edition, "ed-1")
    }

    // MARK: - Order, because the journey reads position

    /// The withheld cards come off the TOP and the survivors keep the server's
    /// order among themselves. The journey's position assertion reads the first
    /// card, so a rig that dropped from the end — or reordered — would leave the
    /// top card identical and the experiment would report no change on a change
    /// that happened.
    func testTheSurvivorsKeepTheServersOwnOrder() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPublishedNetworkFeed: true, drop: 1)

        XCTAssertEqual(staged.items, ["b", "c", "d", "e"])
    }

    // MARK: - The CONTAINER, warm and cold, which is where the rule was wrong

    /// 🔴 **THE REGRESSION THIS SECTION EXISTS FOR.** Every assertion above passes
    /// with the call site handing `rigStagedRefresh` the wrong witness, because a
    /// pure function cannot see which `Bool` its caller computed. The witness was
    /// `!items.isEmpty` — and **the last-good cache seed is a paint** — so in a
    /// warm container the FIRST network load was already staged. The journey's
    /// BEFORE and its AFTER were then both shortened by the same amount, it
    /// measured `SERVED 20 → 20`, and it reported *the feed did not change* about
    /// a refresh that had published correctly.
    ///
    /// It passed in isolation and failed inside the class run, on one build:
    /// `native-uitest.sh` uninstalls once per INVOCATION, so every test after the
    /// first inherits a warm cache. That is a broken gate, not a finding, and the
    /// withdrawn journey of `928a40736` is what it cost.
    ///
    /// So this asserts the experiment's precondition from the container's side,
    /// which no assertion in this file previously could.
    @MainActor
    func testTheFirstNetworkPublicationOfAWarmContainerIsNotStaged() async throws {
        let vm = Self.viewModel(
            cacheSeed: try Self.cached(ids: [901, 902, 903]),
            network: [try Self.response(ids: Array(1...12)), try Self.response(ids: Array(1...12))],
            drop: 4)

        let seeded = await vm.load()

        XCTAssertEqual(seeded, .published)
        XCTAssertEqual(
            vm.items.count, 12,
            "THE WARM-CONTAINER CONFOUND. The cache seed painted 3 cards before the network answered, "
            + "so a witness of `!items.isEmpty` reads TRUE here and stages the very payload the "
            + "experiment measures against — leaving BEFORE and AFTER identically shortened and the "
            + "journey reporting that the feed did not change."
        )

        let refreshed = await vm.load()

        XCTAssertEqual(refreshed, .published)
        XCTAssertEqual(
            vm.items.count, 8,
            "the refresh AFTER the first publication is the one the rig stages, and withholding 4 of "
            + "12 is the controlled difference the journey reads"
        )
    }

    /// The control, and it is the reason the assertion above is about the
    /// CONTAINER rather than about the rig. Same view model, same drop, same
    /// responses, no cache — the arm that was already green. Both containers must
    /// now produce one unstaged payload followed by one staged one, so the
    /// experiment no longer depends on which test ran before it.
    @MainActor
    func testTheFirstNetworkPublicationOfAColdContainerIsNotStagedEither() async throws {
        let vm = Self.viewModel(
            cacheSeed: nil,
            network: [try Self.response(ids: Array(1...12)), try Self.response(ids: Array(1...12))],
            drop: 4)

        await vm.load()
        XCTAssertEqual(vm.items.count, 12)

        await vm.load()
        XCTAssertEqual(
            vm.items.count, 8,
            "a cold container must reach the same staged state as a warm one, or the journey's result "
            + "still depends on the container it inherited"
        )
    }

    /// The witness itself, asserted where it is written rather than through the
    /// feed it changes: a paint is not a publication. A cache seed followed by a
    /// FAILED network attempt leaves cards on screen behind the "couldn't refresh"
    /// banner — items non-empty, nothing the server sent this session — and that
    /// is precisely the state the old read scored as "already published".
    @MainActor
    func testACachePaintWithNoNetworkPublicationNeverSatisfiesTheWitness() async throws {
        let vm = Self.viewModel(
            cacheSeed: try Self.cached(ids: [901, 902, 903]),
            network: [],
            drop: 4)

        XCTAssertFalse(vm.hasPublishedNetworkFeed, "a fresh view model has published nothing")

        await vm.load()

        XCTAssertFalse(
            vm.items.isEmpty,
            "precondition: the seed painted and the failed refresh kept it, so `!items.isEmpty` is "
            + "TRUE — this is the state the two reads disagree about"
        )
        XCTAssertFalse(
            vm.hasPublishedNetworkFeed,
            "A CACHE SEED IS NOT A PUBLICATION. Scoring it as one is what staged the first network "
            + "load of every warm container."
        )
    }

    /// And the positive half of that control: the flag must actually move, or the
    /// rig is inert in both containers and every assertion above is vacuous.
    @MainActor
    func testAPublishingLoadIsWhatSetsTheWitness() async throws {
        let vm = Self.viewModel(
            cacheSeed: nil, network: [try Self.response(ids: Array(1...12))], drop: nil)

        XCTAssertFalse(vm.hasPublishedNetworkFeed)

        let outcome = await vm.load()

        XCTAssertEqual(outcome, .published)
        XCTAssertTrue(vm.hasPublishedNetworkFeed)
    }

    /// The ARMED witness the journey skips on, and it carries both halves of
    /// "armed" in one number — which is the only reason one number is enough.
    ///
    /// 🔴 Measured, not imagined: a run reported `SERVED 50 → 50` after this
    /// repair and looked exactly like the defect. It was the fix working. The
    /// container's cache seeded the page, the first NETWORK load failed, so the
    /// reader's pull became the first publication and was correctly left unstaged.
    /// Without a witness that says "no payload A yet", a journey reads that as
    /// *the refresh published and the reader saw nothing* — the product verdict,
    /// from an experiment that never ran.
    @MainActor
    func testTheArmedWitnessIsZeroUntilThereIsSomethingToMeasureAgainst() async throws {
        let vm = Self.viewModel(
            cacheSeed: try Self.cached(ids: [901, 902, 903]),
            network: [try Self.response(ids: Array(1...12)), try Self.response(ids: Array(1...12))],
            drop: 4)

        XCTAssertEqual(vm.rigChangedRefreshDropArmed, 0, "nothing is armed before any load")

        await vm.load()

        XCTAssertEqual(
            vm.rigChangedRefreshDropArmed, 4,
            "after the first publication the experiment IS armed: payload A exists and the drop was "
            + "read. A journey may pull now."
        )
    }

    /// The other half, and the one that stops the witness from being a constant: a
    /// load that never published must leave it at zero even though the argument
    /// arrived and the page is full of cards.
    @MainActor
    func testTheArmedWitnessStaysZeroWhenTheFirstNetworkLoadFails() async throws {
        let vm = Self.viewModel(
            cacheSeed: try Self.cached(ids: [901, 902, 903]), network: [], drop: 4)

        await vm.load()

        XCTAssertFalse(vm.items.isEmpty, "precondition: the cache seed is on screen")
        XCTAssertEqual(
            vm.rigChangedRefreshDropArmed, 0,
            "THE RUN THAT LOOKED LIKE THE DEFECT. A full page and an armed launch argument, and "
            + "still nothing to measure against — the next pull would be the first publication and "
            + "correctly unstaged. The journey must skip here, not report a finding."
        )
    }

    // MARK: - Fixtures for the container tests

    private nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [FeedResponse]

        init(_ script: [FeedResponse]) { self.script = script }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            await Task.yield()
            return try lock.withLock {
                guard !script.isEmpty else { throw URLError(.notConnectedToInternet) }
                return script.removeFirst()
            }
        }
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    /// Retry budgets are zeroed so a scripted failure reaches its terminal in the
    /// test's own time rather than sleeping through the real backoff.
    @MainActor
    private static func viewModel(
        cacheSeed: CachedDiscoverFeed?, network: [FeedResponse], drop: Int?
    ) -> DiscoverViewModel {
        let vm = DiscoverViewModel(
            client: ScriptedClient(network),
            lastGood: cacheSeed.map { FakeLastGood($0) },
            telemetry: nil,
            retryBudget: 0,
            seededRetryBudget: 0,
            retryBackoff: 0,
            autoRecoveryDelays: [])
        vm.rigChangedRefreshDropOverride = drop
        return vm
    }

    private static func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    private static func response(ids: [Int], limit: Int = 50) throws -> FeedResponse {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":\(limit),"offset":0,"has_more":true}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
    }

    private static func cached(ids: [Int]) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try response(ids: ids, limit: 200),
            storedAt: Date(),
            ttlSeconds: 5,
            identity: "anon:s1")
    }

    // MARK: - The CALL SITE, which no assertion above can reach

    /// 🔴 THE MUTANT THIS FILE OTHERWISE CANNOT KILL. Every rule above passes
    /// with `rigStagedRefresh` called by nobody: a perfect pure function wired
    /// into nothing, and a journey that quietly measures an unchanged refresh and
    /// reports the feed did not change. That is #4624's survivor, #7077's two
    /// photographed defects and native/243's mutant 1 — the same shape three
    /// times, and the reason this suite scans its own call site as source.
    ///
    /// Comments are stripped before matching (see `codeText`), so the long
    /// explanation sitting at the call site cannot satisfy the test that checks
    /// the call site. The 1472 suite records paying exactly that price.
    func testLoadStagesTheRigsPayloadAtTheOnePlaceThePayloadBecomesTheFeed() {
        let source = Self.codeText(of: "Bain Luck/ViewModels/DiscoverViewModel.swift")

        XCTAssertTrue(
            source.contains("Self.rigStagedRefresh("),
            "Nothing calls rigStagedRefresh. Every rule in this file still passes and the rig is inert: "
            + "the journey pulls, the response is unchanged, and it reports that the feed did not change."
        )
        XCTAssertTrue(
            source.contains("let renderable = staged.items"),
            "The rendered list is no longer the staged one, so the withheld cards come back and the "
            + "controlled change never reaches the screen."
        )
        XCTAssertTrue(
            source.contains("incomingEdition: staged.edition"),
            "The reconcile decision reads the RAW edition, so a staged list is judged by the token of "
            + "the list it replaced — it reconciles in place and the journey silently exercises the "
            + "branch that runs when nothing changed."
        )
        XCTAssertTrue(
            source.contains("paintedEdition = staged.edition"),
            "The token recorded as painted describes a list that was never painted, so the NEXT refresh "
            + "compares against a token no list ever had."
        )
        XCTAssertTrue(
            source.contains("hasPublishedNetworkFeed: hasPublishedNetworkFeed"),
            "The rig's witness is no longer the publication flag. If it has gone back to `!items.isEmpty` "
            + "or any other paint-shaped read, a warm container stages the payload the experiment measures "
            + "AGAINST and the journey reports that the feed did not change — green in isolation, red in "
            + "its class, on one build."
        )
        XCTAssertEqual(
            source.components(separatedBy: "hasPublishedNetworkFeed = true").count - 1, 1,
            "The witness must have exactly ONE writer. A second one — a cache seed, a kept-last-good "
            + "banner, a pagination splice — reopens the confound this section repaired; zero makes the "
            + "rig inert in every container."
        )
    }

    /// The affordance withholds CARDS, which no other rig flag does — a shipping
    /// build that honoured it would serve a shortened feed and nothing on screen
    /// would say so. The protection is not a convention, it is that the call site
    /// is compiled out of Release.
    func testTheRigsOnlyCallSiteIsCompiledOutOfAShippingBuild() {
        let source = Self.codeText(of: "Bain Luck/ViewModels/DiscoverViewModel.swift")

        XCTAssertTrue(
            source.contains(
                "#if DEBUG\n                let rigDrop = rigChangedRefreshDropOverride "
                + "?? LaunchRig.changedRefreshDrop()"),
            "The only read of the changed-refresh flag is no longer behind #if DEBUG. A TestFlight "
            + "reader could then shorten their own feed with a launch argument, and the failure would "
            + "look like a backend defect. (The unit-test override sits inside the same #if and falls "
            + "through to the real argument read when nil, so the simulator journey is unaffected.)"
        )
        XCTAssertTrue(
            source.contains("#else\n                let rigDrop: Int? = nil"),
            "Release must supply a compile-time nil rather than falling through to whatever the flag "
            + "last read."
        )
    }

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

    /// String-aware, and deliberately the same implementation as the 1472 and
    /// #7074 pull suites, so three scans of one file cannot read it differently.
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

    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
