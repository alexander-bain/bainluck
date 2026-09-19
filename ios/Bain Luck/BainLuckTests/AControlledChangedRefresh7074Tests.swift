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
            items: painted, edition: "ed-1", hasPaintedFeed: true, drop: nil)

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
            items: [String](), edition: nil, hasPaintedFeed: true, drop: nil)
        XCTAssertTrue(empty.items.isEmpty)
        XCTAssertNil(empty.edition)
    }

    // MARK: - The controlled change itself

    func testAStagedRefreshWithholdsTheFirstCardsSoTheTopOfTheFEEDCHANGES() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPaintedFeed: true, drop: 2)

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
            items: painted, edition: "ed-1", hasPaintedFeed: true, drop: 2)

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
            items: painted, edition: nil, hasPaintedFeed: true, drop: 2)

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

    /// The first paint is payload A — the thing the change is measured AGAINST.
    /// Shortening it too would leave the journey comparing two shortened lists
    /// and reporting the difference between them as the experiment's result.
    func testTheFirstPaintIsNeverShortened() {
        let staged = VM.rigStagedRefresh(
            items: painted, edition: "ed-1", hasPaintedFeed: false, drop: 2)

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
                items: painted, edition: "ed-1", hasPaintedFeed: true, drop: oversized)

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
            items: ["only"], edition: "ed-1", hasPaintedFeed: true, drop: 3)

        XCTAssertEqual(staged.items, ["only"])
        XCTAssertEqual(
            staged.edition, "ed-1",
            "an unchanged list must keep its unchanged token, or the reader takes a wholesale "
            + "repaint to arrive at exactly the cards they already had"
        )
    }

    func testAnEmptyPayloadIsLeftAloneRatherThanRestamped() {
        let staged = VM.rigStagedRefresh(
            items: [String](), edition: "ed-1", hasPaintedFeed: true, drop: 2)

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
            items: painted, edition: "ed-1", hasPaintedFeed: true, drop: 1)

        XCTAssertEqual(staged.items, ["b", "c", "d", "e"])
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
    }

    /// The affordance withholds CARDS, which no other rig flag does — a shipping
    /// build that honoured it would serve a shortened feed and nothing on screen
    /// would say so. The protection is not a convention, it is that the call site
    /// is compiled out of Release.
    func testTheRigsOnlyCallSiteIsCompiledOutOfAShippingBuild() {
        let source = Self.codeText(of: "Bain Luck/ViewModels/DiscoverViewModel.swift")

        XCTAssertTrue(
            source.contains("#if DEBUG\n                let rigDrop = LaunchRig.changedRefreshDrop()"),
            "The only read of the changed-refresh flag is no longer behind #if DEBUG. A TestFlight "
            + "reader could then shorten their own feed with a launch argument, and the failure would "
            + "look like a backend defect."
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
