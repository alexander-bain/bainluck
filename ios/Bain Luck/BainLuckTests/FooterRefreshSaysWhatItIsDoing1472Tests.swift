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
            let copy = ((shown.status ?? "") + " " + shown.title).lowercased()
            for word in banned {
                XCTAssertFalse(
                    copy.contains(word),
                    "\(phase) puts '\(word)' on a reader's screen: '\(copy.trimmingCharacters(in: .whitespaces))'"
                )
            }
        }
    }

    // MARK: - The call sites

    /// Both end-card call sites hand the card the LIVE phase.
    ///
    /// Read as text because the fact is about a file. `phase` has no default, so
    /// the compiler forces each site to answer — but a site can answer with a
    /// literal, and `phase: .idle` compiles, passes every test above, and ships
    /// this entire fix inert. That is the failure mode this test exists for.
    func testBothEndCardCallSitesPassTheLiveRefreshPhase() throws {
        let source = try String(
            contentsOf: Self.projectDirectory.appendingPathComponent("Bain Luck/Views/DiscoverView.swift"),
            encoding: .utf8
        )

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
            searched = call.upperBound..<source.endIndex
        }

        XCTAssertEqual(
            sites, 2,
            "Discover built \(sites) end cards; #1472 knows of two (the empty-eligible caught-up state and "
            + "the bottom-of-feed footer). A new one needs its own phase, and this count needs updating with it."
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
    func testEveryResolutionsFetchIsGatedOnTheSurfaceThatDrawsIt() throws {
        let source = try String(
            contentsOf: Self.projectDirectory.appendingPathComponent("Bain Luck/Views/DiscoverView.swift"),
            encoding: .utf8
        )

        var searched = source.startIndex..<source.endIndex
        var fetches = 0
        while let call = source.range(of: "fetchResolutions()", range: searched) {
            fetches += 1
            // The gate is the nearest one ABOVE the call, so look back over the
            // enclosing statement rather than forward.
            let preceding = source[..<call.lowerBound].suffix(400)
            XCTAssertTrue(
                preceding.contains("ReleaseSurfaces.predictionsExperienceEnabled"),
                "Resolutions fetch \(fetches) is ungated. Nothing in the launch build draws what it returns, "
                + "and on the refresh path it holds the reader's pull open for the round trip. Context:\n\(preceding.suffix(200))"
            )
            searched = call.upperBound..<source.endIndex
        }

        XCTAssertEqual(fetches, 2, "Discover makes \(fetches) resolutions fetches; #1472 gated two (cold open and refresh).")
    }

    /// The success confirmation is scheduled OUTSIDE the awaited refresh closure.
    ///
    /// Sleeping for the confirmation window inside `refreshFeed()` would keep
    /// `.refreshable`'s spinner — and the header it pushes down — on screen for
    /// that window on every single pull, which is the other half of Alex's
    /// September 16 report ("pull-to-refresh leaves heading/cards frozen halfway
    /// down screen"). This fix must not manufacture it.
    func testTheConfirmationTimerDoesNotHoldTheRefreshClosure() throws {
        let source = try String(
            contentsOf: Self.projectDirectory.appendingPathComponent("Bain Luck/Views/DiscoverView.swift"),
            encoding: .utf8
        )
        let body = try XCTUnwrap(
            source.range(of: "private func refreshFeed() async {"),
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

    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
