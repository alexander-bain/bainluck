import XCTest
@testable import Bain_Luck

/// #1472 — "Bottom Refresh produces no visible response or loading feedback"
/// (Alex's September 16 physical-phone test, recorded on #6444).
///
/// ## The defect, and why nothing caught it
///
/// The button was not broken. `NativeFeedEndCard`'s Refresh control ran
/// `DiscoverView.refreshFeed()` exactly as #1773 intended. It just rendered the
/// same pixels whether a refresh was in flight, had finished, or had failed —
/// and so did the rest of the page at that end of it:
///
///   * `DiscoverViewModel.load()` raises its blocking `loading` flag only
///     `if items.isEmpty`, deliberately (#1465: revalidate behind last-good
///     content, never blank it). At the bottom of a populated feed there is
///     therefore no spinner anywhere.
///   * A failed refresh sets `refreshFailedShowingCache`, and the banner reading
///     it is drawn at the TOP of the scroll view. The reader who pressed the
///     button is at the bottom of that same scroll view.
///   * A refresh returning the same markets is a correct refresh. The cards not
///     changing is the common case, not a symptom.
///
/// Three absent signals compose into "nothing happened". No existing test could
/// see it, because each of the three is individually correct.
///
/// ## What is pinned here
///
/// The presentation rule is pure, so it is pinned directly. The property that
/// actually failed is a property of the SET — all four phases looked alike — so
/// `testEveryPhaseLooksDifferentFromEveryOther` states that, rather than relying
/// on four independent pins to imply it.
///
/// The last test reads `DiscoverView.swift` as TEXT. A view parameter is a guard
/// that can ship disarmed: every test in this file builds its own card, so not
/// one of them can see what the real page passes, and a call site that answered
/// the compiler with `phase: .idle` would leave the whole file green while the
/// reader saw the September 16 behaviour unchanged. Same idiom, same reason, as
/// `APreKickoffCertaintyIsNotALivePriceTests`.
final class FooterRefreshSaysWhatItIsDoing1472Tests: XCTestCase {

    private typealias Phase = NativeFeedRefreshPhase

    private static let allPhases: [Phase] = [.idle, .refreshing, .refreshed, .failed]

    // MARK: - The property that failed

    /// The whole defect in one assertion: a reader must be able to tell these
    /// four states apart without being told which one they are in.
    ///
    /// Pairwise over the full set, so adding a fifth phase that duplicates an
    /// existing one reds here rather than shipping as a silent state.
    func testEveryPhaseLooksDifferentFromEveryOther() {
        let presentations = Self.allPhases.map {
            (phase: $0, shown: NativeFeedEndCard.refreshPresentation($0))
        }

        for i in presentations.indices {
            for j in presentations.indices where j > i {
                XCTAssertNotEqual(
                    presentations[i].shown, presentations[j].shown,
                    "\(presentations[i].phase) and \(presentations[j].phase) render identically. "
                    + "That is the #1472 defect itself: the reader pressed Refresh and the page "
                    + "gave back the same thing it showed before the press."
                )
            }
        }
    }

    /// THE SAME DEFECT, ONE READER OVER — and it is not hypothetical.
    ///
    /// A SwiftUI `Button` carrying an explicit `.accessibilityLabel` **replaces**
    /// its children in the accessibility tree: the `Text(title)` inside it stops
    /// being an element. The first cut of this fix gave the button one fixed
    /// label, so a VoiceOver reader heard "Refresh feed" in all four phases
    /// while a sighted reader saw four different things — #1472 intact for them.
    ///
    /// Caught by `AReaderCanSeeTheFooterRefreshWorking1472Tests`, which tapped
    /// the real control on a real build and could not find "Refreshing…"
    /// anywhere in the tree afterwards.
    func testEveryPhaseSoundsDifferentFromEveryOtherToo() {
        let labels = Self.allPhases.map { NativeFeedEndCard.refreshPresentation($0).accessibilityLabel }
        XCTAssertEqual(
            Set(labels).count, Self.allPhases.count,
            "Two phases announce themselves identically, so a reader who cannot see the control cannot tell "
            + "them apart: \(labels)"
        )
        for (phase, label) in zip(Self.allPhases, labels) {
            XCTAssertFalse(
                label.trimmingCharacters(in: .whitespaces).isEmpty,
                "\(phase) has no spoken name at all"
            )
        }
    }

    /// The spoken label carries the outcome, because the status line beside it is
    /// `accessibilityHidden` — otherwise the outcome would be read twice, or (if
    /// the label were phase-blind) not at all.
    func testTheSpokenLabelCarriesTheOutcomeItsPhaseHas() {
        XCTAssertTrue(
            NativeFeedEndCard.refreshPresentation(.refreshing).accessibilityLabel.lowercased().contains("refreshing"),
            "the in-flight phase does not announce that it is in flight"
        )
        XCTAssertTrue(
            NativeFeedEndCard.refreshPresentation(.failed).accessibilityLabel.lowercased().contains("couldn't refresh"),
            "the failed phase does not announce the failure, and the visible status line is hidden from VoiceOver"
        )
        XCTAssertTrue(
            NativeFeedEndCard.refreshPresentation(.refreshed).accessibilityLabel.lowercased().contains("checked"),
            "the finished phase does not announce that it finished"
        )
    }

    /// `.idle` is the only phase in which the reader has not asked for anything,
    /// so it is the only one that may be silent.
    func testOnlyIdleIsSilent() {
        XCTAssertNil(NativeFeedEndCard.refreshPresentation(.idle).status)

        for phase in Self.allPhases where phase != .idle {
            let shown = NativeFeedEndCard.refreshPresentation(phase)
            let speaks = shown.status != nil
                || shown.title != NativeFeedEndCard.refreshPresentation(.idle).title
                || shown.systemImage != NativeFeedEndCard.refreshPresentation(.idle).systemImage
            XCTAssertTrue(
                speaks,
                "\(phase) is indistinguishable from never having pressed the button."
            )
        }
    }

    // MARK: - In flight

    func testRefreshingSaysSoAndShowsASpinnerInPlaceOfTheGlyph() {
        let shown = NativeFeedEndCard.refreshPresentation(.refreshing)
        XCTAssertEqual(shown.title, "Refreshing…")
        XCTAssertNil(
            shown.systemImage,
            "a nil glyph is the spinner's seat — the in-flight phase is the one phase that must animate"
        )
    }

    /// The press must not be re-accepted while it is being served. A second tap
    /// re-enters `refreshFeed()`, which resets `visibleCount` and ages the
    /// dismiss store again for a request already on the wire.
    func testRefreshingIsTheOnlyPhaseThatRefusesATap() {
        XCTAssertFalse(NativeFeedEndCard.refreshPresentation(.refreshing).isEnabled)

        for phase in Self.allPhases where phase != .refreshing {
            XCTAssertTrue(
                NativeFeedEndCard.refreshPresentation(phase).isEnabled,
                "\(phase) is a resting state and must accept a tap — a control that is dead at rest is worse than one that is silent"
            )
        }
    }

    // MARK: - Finished

    /// Says what was CHECKED, never what was found.
    ///
    /// A refresh that returns the same markets is a correct refresh, and the
    /// common one. "New markets" or a count would be a claim this card cannot
    /// support, and would read as a failure on every honest no-change refresh.
    func testSuccessConfirmsTheCheckAndPromisesNoNewContent() {
        let shown = NativeFeedEndCard.refreshPresentation(.refreshed)
        XCTAssertEqual(shown.status, "Checked just now")
        XCTAssertTrue(shown.isEnabled, "the reader may check again immediately")

        let claimsContent = ["new", "found", "added", "more markets"]
            .contains { shown.status?.lowercased().contains($0) == true }
        XCTAssertFalse(
            claimsContent,
            "the confirmation claims content it cannot know about: \(shown.status ?? "nil")"
        )
    }

    /// The confirmation decays. A success line that never expires becomes false
    /// by sitting still, which is the class of defect this card exists to avoid.
    func testTheSuccessConfirmationHasABoundedLife() {
        XCTAssertGreaterThan(DiscoverView.refreshConfirmationWindow, 0)
        XCTAssertLessThanOrEqual(
            DiscoverView.refreshConfirmationWindow, 10,
            "\"Checked just now\" stops being true long before this; it is a confirmation, not a status field"
        )
    }

    // MARK: - Failed

    /// The failure is the reader's only notice of it — the banner that would
    /// otherwise say so is drawn at the far end of the scroll view — so it must
    /// both say so and carry the retry.
    func testFailureNamesItselfAndOffersTheRetry() {
        let shown = NativeFeedEndCard.refreshPresentation(.failed)
        XCTAssertEqual(shown.status, "Couldn't refresh")
        XCTAssertEqual(shown.title, "Try again")
        XCTAssertTrue(shown.isEnabled, "a failure the reader cannot retry from is a dead end")
    }

    /// Reader-facing copy, so notice 33/34 apply: no jargon, no diagnostics, no
    /// banned vocabulary anywhere in the control.
    func testNoPhaseSpeaksInJargon() {
        let banned = ["book", "bookmaker", "cache", "payload", "endpoint", "api",
                      "http", "request", "nil", "error code", "retry budget"]
        for phase in Self.allPhases {
            let shown = NativeFeedEndCard.refreshPresentation(phase)
            let copy = ((shown.status ?? "") + " " + shown.title + " " + shown.accessibilityLabel).lowercased()
            for word in banned {
                XCTAssertFalse(
                    copy.contains(word),
                    "\(phase) puts '\(word)' on a reader's screen: '\(copy.trimmingCharacters(in: .whitespaces))'"
                )
            }
        }
    }

    // MARK: - The card has to still be there to speak

    /// The two speaking phases outrank the pagination spinner in the footer.
    ///
    /// MEASURED, and it is the reason the first cut of this fix was invisible:
    /// `refreshFeed` resets `visibleCount` to 20 as its first visible act, the
    /// surviving cards' `onAppear` calls `loadMoreIfNeeded()`, `vm.loadingMore`
    /// goes true within a frame — and the footer's plain ordering drew a
    /// wordless `ProgressView` in place of the card the reader had just pressed.
    /// The journey test reported the in-flight control not hittable for exactly
    /// as long as that was true.
    func testTheSpeakingPhasesOutrankThePaginationSpinner() {
        XCTAssertTrue(
            DiscoverView.footerKeepsTheCard(phase: .refreshing),
            "a refresh in flight yields the footer to a wordless spinner, so the press has no voice"
        )
        XCTAssertTrue(
            DiscoverView.footerKeepsTheCard(phase: .failed),
            "a pagination spinner swallows the only notice a failed refresh gets at this end of the page"
        )

        // AND THE QUIET PHASES MUST NOT, or the end card would sit over a feed
        // that has more to give, claiming the reader is caught up.
        XCTAssertFalse(
            DiscoverView.footerKeepsTheCard(phase: .idle),
            "'You're all caught up' would draw over a feed that is still paginating"
        )
        XCTAssertFalse(DiscoverView.footerKeepsTheCard(phase: .refreshed))
    }

    /// The footer consults that rule BEFORE it consults `loadingMore`. Ordering
    /// is the whole content of the fix, and it is not visible in the rule.
    func testTheFooterAsksAboutTheCardBeforeItAsksAboutPagination() throws {
        let lines = Self.codeLines(of: "Bain Luck/Views/DiscoverView.swift")
        let keeps = try XCTUnwrap(
            lines.lastIndex(where: { $0.contains("Self.footerKeepsTheCard(phase: footerRefreshPhase)") }),
            "the footer no longer consults the keep-the-card rule at all"
        )
        let spinner = try XCTUnwrap(
            lines.lastIndex(where: { $0.contains("} else if vm.loadingMore {") }),
            "the footer's pagination spinner has moved; move this test with it"
        )
        XCTAssertLessThan(
            keeps, spinner,
            "the footer asks `loadingMore` first, so a refresh the reader started from the end card is "
            + "answered by a wordless spinner where the card used to be — the defect this fix exists for."
        )
    }

    // MARK: - The call sites

    /// Both end-card call sites hand the card the LIVE phase.
    ///
    /// Read as text because the fact is about a file. `phase` has no default, so
    /// the compiler forces each site to answer — but a site can answer with a
    /// literal, and `phase: .idle` compiles, passes every test above, and ships
    /// this entire fix inert. That is the failure mode this test exists for.
    func testBothEndCardCallSitesPassTheLiveRefreshPhase() throws {
        // Comment-stripped, like every scan here: a doc comment naming
        // `phase: footerRefreshPhase` would otherwise satisfy this on a call
        // site that passes a literal.
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        XCTAssertFalse(source.isEmpty, "DiscoverView.swift could not be read; this test proves nothing.")

        var searched = source.startIndex..<source.endIndex
        var sites = 0
        while let call = source.range(of: "NativeFeedEndCard(", range: searched) {
            let arguments = source[call.upperBound...].prefix(200)
            sites += 1
            XCTAssertTrue(
                arguments.contains("phase: footerRefreshPhase"),
                "End-card call site \(sites) does not pass the live phase, so the control is frozen on "
                + "whatever it was given however right the rule is. Found instead:\n\(arguments)"
            )
            XCTAssertTrue(
                arguments.contains("refreshFeed(returningToTopWith: feedProxy)"),
                "End-card call site \(sites) refreshes without returning the reader anywhere, so the press "
                + "strands them mid-scroll in a feed they have not seen. Found instead:\n\(arguments)"
            )
            searched = call.upperBound..<source.endIndex
        }

        XCTAssertEqual(
            sites, 3,
            "Discover built \(sites) end cards; #1472 knows of three — the empty-eligible caught-up state, "
            + "the footer's keep-the-card branch (a refresh the reader started here), and the footer's "
            + "ordinary end-of-feed branch. A new one needs its own phase, and this count with it."
        )
    }

    /// A footer refresh returns the reader to the top of the fresh feed, and
    /// only when it SUCCEEDED.
    ///
    /// MEASURED on a real build before this existed (journey run 2026-09-16,
    /// badge `SERVED 49 · DRAWN 49 · FEED 3 · PULLS 1`): the press ran the
    /// refresh, `visibleCount` reset collapsed the ~150-card page, the end card
    /// unmounted because the fresh page-1 load set `hasMore` back to true, and
    /// the scroll offset survived against entirely different content. The reader
    /// pressed a button at the end of the feed and landed, unmarked, part-way
    /// down a feed they had never seen.
    ///
    /// Read as text for the same reason as the call-site test: the scroll is a
    /// side effect on a `ScrollViewProxy` that no unit-testable value records.
    func testAFooterRefreshReturnsTheReaderToTheTopAndOnlyOnSuccess() throws {
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        let body = try XCTUnwrap(source.range(of: "private func refreshFeed("))
        let scope = String(source[body.upperBound...].prefix(2000))

        let scroll = try XCTUnwrap(
            scope.range(of: "proxy.scrollTo(Self.feedTopAnchor"),
            "A footer refresh no longer returns the reader anywhere. Without it the press lands them "
            + "mid-scroll in a feed they have not seen, which reads as 'nothing happened' with extra steps."
        )

        // The return must sit inside the success arm. A scroll on the failure
        // arm would tear the reader away from the only notice they get.
        let beforeScroll = scope[..<scroll.lowerBound]
        let successArm = try XCTUnwrap(
            beforeScroll.range(of: "if vm.error == nil {", options: .backwards),
            "the scroll-to-top is not guarded by the success test"
        )
        XCTAssertFalse(
            beforeScroll[successArm.upperBound...].contains("} else {"),
            "the scroll-to-top has fallen out of the success arm — a failed refresh must leave the reader "
            + "where they are, next to the 'Couldn't refresh' notice that is their only word on it."
        )

        // The anchor it scrolls to has to exist in the view.
        XCTAssertTrue(
            source.contains(".id(Self.feedTopAnchor)"),
            "nothing in the feed carries the top anchor, so scrolling to it is a no-op"
        )
    }

    /// Pull-to-refresh must NOT get the scroll-return: that reader is already at
    /// the top, and the `.refreshable` closure takes no proxy.
    func testPullToRefreshDoesNotAskForTheScrollReturn() throws {
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        let refreshable = try XCTUnwrap(
            source.range(of: ".refreshable {"),
            "Discover no longer has a pull-to-refresh; move this test with it."
        )
        let closure = source[refreshable.upperBound...].prefix(120)
        XCTAssertFalse(
            closure.contains("returningToTopWith"),
            "pull-to-refresh is asking for a scroll-to-top it does not need. Found:\n\(closure)"
        )
    }

    /// The refresh path does not hold the reader's gesture open on a fetch
    /// nothing renders.
    ///
    /// `.refreshable` pins the header down until its closure returns, and
    /// `refreshFeed()` awaited `fetchResolutions()` after the feed load. The only
    /// view that reads `resolutions` is the digest card, which is behind
    /// `ReleaseSurfaces.predictionsExperienceEnabled` — `false` in the launch
    /// build. So every pull-to-refresh paid a second network round trip for a
    /// value the shipping app cannot draw.
    /// MEASURED VACUOUS ONCE, AND THAT IS WHY IT READS CODE LINES NOW.
    ///
    /// The first draft looked back 400 raw characters from the call for the flag
    /// name. Mutant M13 removed the gate from the refresh path and the suite
    /// stayed GREEN: the 400-character window still held the *comment* above the
    /// call, which names `ReleaseSurfaces.predictionsExperienceEnabled` in prose
    /// explaining why the gate is there. The assertion was matching its own
    /// documentation. So comments are stripped first, and the window is a small
    /// number of CODE lines rather than a character count.
    func testEveryResolutionsFetchIsGatedOnTheSurfaceThatDrawsIt() throws {
        let lines = Self.codeLines(of: "Bain Luck/Views/DiscoverView.swift")

        let fetchLines = lines.indices.filter { lines[$0].contains("fetchResolutions()") }
        XCTAssertEqual(
            fetchLines.count, 2,
            "Discover makes \(fetchLines.count) resolutions fetches; #1472 gated two (cold open and refresh)."
        )

        for line in fetchLines {
            // The gate sits in the enclosing `if`, which is at most a couple of
            // code lines above the call at either site.
            let window = lines[max(0, line - Self.gateLookbackLines)...line].joined(separator: "\n")
            XCTAssertTrue(
                window.contains("ReleaseSurfaces.predictionsExperienceEnabled"),
                "The resolutions fetch at code line \(line) is ungated. Nothing in the launch build draws what "
                + "it returns, and on the refresh path it holds the reader's pull open for the round trip. Code:\n\(window)"
            )
        }
    }

    /// How far above a call its gate may sit. Small on purpose: a generous window
    /// is how a source scan stops discriminating.
    private static let gateLookbackLines = 3

    /// The success confirmation is scheduled OUTSIDE the awaited refresh closure.
    ///
    /// Sleeping for the confirmation window inside `refreshFeed()` would keep
    /// `.refreshable`'s spinner — and the header it pushes down — on screen for
    /// that window on every single pull, which is the other half of Alex's
    /// September 16 report ("pull-to-refresh leaves heading/cards frozen halfway
    /// down screen"). This fix must not manufacture it.
    func testTheConfirmationTimerDoesNotHoldTheRefreshClosure() throws {
        let source = Self.codeText(of: "Bain Luck/Views/DiscoverView.swift")
        XCTAssertFalse(source.isEmpty, "DiscoverView.swift could not be read; this test proves nothing.")
        let body = try XCTUnwrap(
            source.range(of: "private func refreshFeed("),
            "refreshFeed has been renamed or moved; move this test with it."
        )
        let scope = source[body.upperBound...].prefix(3000)
        let sleepCall = try XCTUnwrap(
            scope.range(of: "Task.sleep"),
            "the confirmation no longer decays on a timer — if it decays another way, repoint this test at that"
        )
        let beforeSleep = scope[..<sleepCall.lowerBound].suffix(200)
        XCTAssertTrue(
            beforeSleep.contains("Task { @MainActor in"),
            "the confirmation window is being awaited by refreshFeed itself, which pins the pull-to-refresh "
            + "header down for its whole duration. Context:\n\(beforeSleep)"
        )
    }

    // MARK: - Reading source as source

    /// A file's lines with comments and blank lines removed.
    ///
    /// Every scan in this file goes through here, because a scan that can match
    /// a comment is a scan that passes on the strength of the sentence written
    /// to explain the code it is supposed to be checking — measured, see
    /// `testEveryResolutionsFetchIsGatedOnTheSurfaceThatDrawsIt`.
    private static func codeLines(of relativePath: String) -> [String] {
        let source = (try? String(
            contentsOf: projectDirectory.appendingPathComponent(relativePath), encoding: .utf8
        )) ?? ""
        return source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { stripComment(String($0)) }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }

    /// One line with any `//` comment removed — but only a `//` that is not
    /// inside a string literal, so a `"https://…"` in real code survives intact.
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

    private static func codeText(of relativePath: String) -> String {
        codeLines(of: relativePath).joined(separator: "\n")
    }

    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
