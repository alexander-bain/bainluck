import Foundation

/// What the reader who PULLED Discover down sees about their own gesture —
/// at the top of the feed, which is where that reader is standing (#7074).
///
/// ═══ THE DEFECT THIS IS THE RULE FOR ═══
///
/// Alex, physical phone, TestFlight 1.0 (15), 2026-09-18: *"Pull gesture briefly
/// shows activity with no apparent change."* #1472 had already found and fixed
/// the same class at the BOTTOM of this feed — the footer's Refresh button, whose
/// four outcomes all rendered byte-identically — and `NativeFeedRefreshPhase`
/// carries that repair. But its only reader is `NativeFeedEndCard`, which draws
/// at the END of the scroll view.
///
/// So the two refresh readers were each given the answer at the other one's end
/// of the page:
///
///   • the FOOTER reader presses a button at the bottom and (#1472) gets the
///     confirmation there, under their thumb;
///   • the PULL reader pulls at the top and gets nothing at all — the phase is
///     set for them exactly as it is for the footer, and the only view that reads
///     it is a screen-and-a-half below the fold.
///
/// Measured on master `2174003b3` by reading the three readers of
/// `footerRefreshPhase` (all in the footer region) and the two error surfaces in
/// `DiscoverView.body`, both of which are gated on `vm.items.isEmpty`: a pull
/// that FAILS while the reader holds a full feed renders nothing, and a pull that
/// SUCCEEDS renders nothing. **Those two states are indistinguishable from each
/// other and from not having pulled**, which is the sentence Alex wrote.
///
/// ═══ WHY THIS IS A RULE AND NOT A VIEW ═══
///
/// Same reason #1472 is: the property is a property of the SET of phases, and a
/// set cannot be asserted from inside a SwiftUI builder returning an opaque type.
/// The view below this is three rows of chrome; every claim worth making — which
/// phases speak, what each says, which one decays, which one carries the retry —
/// is made here, where a test can call it.
///
/// ═══ THE COPY IS BORROWED, DELIBERATELY ═══
///
/// Every word this can print is `NativeFeedEndCard.refreshPresentation(_:).status`
/// for the same phase. One refresh, two places a reader may be standing, one
/// vocabulary (standing notice 35 — a surface does not get bespoke copy for a
/// state another surface already names). `testTheNoticeSpeaksTheFootersWords`
/// is that sentence written down, so a copy change to one can never silently
/// leave the two disagreeing about what just happened.
struct DiscoverPullRefreshNotice: Equatable {
    /// The one short line the reader sees. Never a diagnostic (D102): it names
    /// the outcome, not the mechanism, and never a count.
    let text: String

    /// The leading glyph. Carried in the rule rather than chosen at the view
    /// because it is one of the two things that separates success from failure
    /// for a reader who is not reading — the same argument `systemImage` is
    /// carried for in `NativeFeedRefreshPresentation`.
    let systemImage: String

    /// Whether the notice carries a retry control.
    ///
    /// Only failure does. A success that offered "try again" would be inviting
    /// the reader to redo work that worked.
    let offersRetry: Bool

    /// Whether the notice clears itself.
    ///
    /// Success decays — "Checked just now" must not still be on screen ten
    /// minutes later, the same bounded life `.refreshed` has at the footer.
    /// Failure does NOT: it is the reader's only notice and it carries the
    /// retry, so it stays until another refresh replaces it.
    let decays: Bool

    /// What the notice is called to a reader who cannot see it.
    ///
    /// Spelled out rather than composed from `text`, because the retry control
    /// makes the failure notice a container whose label replaces its children —
    /// the exact trap `NativeFeedRefreshPresentation.accessibilityLabel` exists
    /// for, one surface over.
    let accessibilityLabel: String

    /// The notice for a phase, or `nil` for the phases that must stay silent.
    ///
    /// TWO PHASES ARE SILENT AND THEY ARE SILENT FOR DIFFERENT REASONS:
    ///
    ///   • `.idle` — nothing has been asked for. A notice here would be a
    ///     permanent fixture at the top of the feed saying nothing.
    ///   • `.refreshing` — **this is the one phase the pull reader can already
    ///     see.** `.refreshable` draws its own spinner under their finger and
    ///     holds it until the closure returns; Alex's report says so in its own
    ///     first clause ("briefly shows activity"). Adding a second in-flight
    ///     marker directly beneath the system's would be two spinners for one
    ///     request. What his sentence says is missing is the SECOND clause — the
    ///     outcome — and that is what the two speaking phases carry.
    ///
    /// The footer answers `.refreshing` because its reader has no system spinner;
    /// this surface has one. Same phase, different reader, and the difference is
    /// which of them can already see it.
    static func forPhase(_ phase: NativeFeedRefreshPhase) -> DiscoverPullRefreshNotice? {
        switch phase {
        case .idle, .refreshing:
            return nil
        case .refreshed:
            return DiscoverPullRefreshNotice(
                text: NativeFeedEndCard.refreshPresentation(.refreshed).status ?? "",
                systemImage: "checkmark.circle.fill",
                offersRetry: false,
                decays: true,
                accessibilityLabel: "Feed refreshed. Checked just now."
            )
        case .failed:
            return DiscoverPullRefreshNotice(
                text: NativeFeedEndCard.refreshPresentation(.failed).status ?? "",
                systemImage: "exclamationmark.triangle.fill",
                offersRetry: true,
                decays: false,
                accessibilityLabel: "Couldn't refresh. Try again."
            )
        }
    }

    /// The accessibility identifier the notice's row carries.
    ///
    /// One constant so the journey test and the view cannot drift — a UI test
    /// hunting a string the view stopped using reports "the notice never
    /// appeared", which is indistinguishable from the defect it is watching for.
    static let identifier = "discover-refresh-notice"

    /// The retry control's identifier, same argument.
    static let retryIdentifier = "discover-refresh-notice-retry"
}
