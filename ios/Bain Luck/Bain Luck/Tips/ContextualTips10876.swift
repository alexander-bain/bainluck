import Combine
import os
import SwiftUI
import TipKit

private let logger = Logger(subsystem: "com.bainluck", category: "tips")

/// #10876 — at most three contextual tips, each anchored to a control that
/// already exists: the bookmark (pin), Start Live Activity, and the game
/// chart's hold-and-slide. No tour, no new control, no permission request.
///
/// Eligibility lives in three layers, each with one job:
/// * TipKit — rules (pin engagement), persistent dismissal, `MaxDisplayCount`,
///   the daily display frequency, and invalidation once the action is used.
///   All of it survives relaunch in TipKit's own datastore.
/// * `ContextualTipEligibility10876` — whether the control is usable right now
///   (pure, unit-tested).
/// * `ContextualTipQueue10876` — one tip on screen, one kind per session.
///
/// iPhone and iPad only for now: the Mac chart selects with the pointer, not a
/// held touch, and no tip's Mac placement has been seen. On macOS and visionOS
/// every anchor below is inert.
@MainActor enum ContextualTips10876 {
    static var isEnabledOnThisPlatform: Bool {
        #if os(iOS)
        true
        #else
        false
        #endif
    }

    private static var configured = false
    private static var chartLearnedThisProcess = false
    private static var firstAsked: Date?

    /// Configured on first use rather than at launch so the app entry is not
    /// touched. TipKit is only consulted after this has run.
    static func configureIfNeeded() {
        guard isEnabledOnThisPlatform, !configured else { return }
        configured = true
        let option = ContextualTipLaunchOption10876.read()
        do {
            if option == .reset { try Tips.resetDatastore() }
            if option == .hidden { Tips.hideAllTipsForTesting() }
            try Tips.configure([
                .displayFrequency(.daily),
                .datastoreLocation(.applicationDefault),
            ])
        } catch {
            logger.error("TipKit configuration failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    static func processAge(now: Date = Date()) -> TimeInterval {
        if let started = ProcessAge10876.startDate() { return now.timeIntervalSince(started) }
        let first = firstAsked ?? now
        firstAsked = first
        return now.timeIntervalSince(first)
    }

    static func pinLearned() {
        guard isEnabledOnThisPlatform else { return }
        configureIfNeeded()
        PinTip10876().invalidate(reason: .actionPerformed)
    }

    static func followLiveLearned() {
        guard isEnabledOnThisPlatform else { return }
        configureIfNeeded()
        FollowLiveTip10876(game: "").invalidate(reason: .actionPerformed)
    }

    /// Called at the end of every chart gesture; writes once per process.
    static func chartLearned() {
        guard isEnabledOnThisPlatform, !chartLearnedThisProcess else { return }
        chartLearnedThisProcess = true
        configureIfNeeded()
        ExploreChartTip10876().invalidate(reason: .actionPerformed)
    }
}

// MARK: - The three tips

/// Pin: the bookmark on an event or market page, after the reader has spent
/// real time with two of them and before they have pinned anything.
nonisolated struct PinTip10876: Tip {
    static let engaged = Tips.Event(id: "bl.tips10876.pin.engaged")

    var id: String { "bl.tips10876.pin" }
    var title: Text { Text("Pin it for later") }
    var message: Text? {
        Text("Tap the bookmark and it stays in My Stuff.")
    }
    var image: Image? { Image(systemName: "bookmark") }
    /// `ContextualTipEligibility10876.pinEngagementsBeforeTip` — a literal
    /// here because the rule macro builds a predicate over the donation store.
    var rules: [Rule] {
        [#Rule(Self.engaged) { $0.donations.count >= 2 }]
    }
    var options: [any TipOption] { [Tips.MaxDisplayCount(2)] }
}

/// Follow live: Start Live Activity on a game that is live now, only while
/// that control is shown and tappable. The copy repeats the control's own
/// promise — it updates while the game is open — and nothing more.
nonisolated struct FollowLiveTip10876: Tip {
    /// The game's own name, "Away vs Home", as the page shares it.
    let game: String

    var id: String { "bl.tips10876.followLive" }
    var title: Text { Text("Follow this game on your Lock Screen") }
    var message: Text? {
        Text("Start Live Activity to keep \(game) on your Lock Screen. It updates while this game is open.")
    }
    var image: Image? { Image(systemName: "dot.radiowaves.left.and.right") }
    var options: [any TipOption] { [Tips.MaxDisplayCount(2)] }
}

/// Explore the chart: the game chart's touch-and-hold scrub (#925), on a line
/// with enough observed moments to explore, before the first scrub.
nonisolated struct ExploreChartTip10876: Tip {
    var id: String { "bl.tips10876.exploreChart" }
    var title: Text { Text("See any moment") }
    var message: Text? {
        Text("Touch and hold the chart, then slide to see the win probability at that time.")
    }
    var image: Image? { Image(systemName: "hand.point.up.left") }
    var options: [any TipOption] { [Tips.MaxDisplayCount(2)] }
}

// MARK: - One tip at a time

@MainActor final class ContextualTipQueueCenter10876: ObservableObject {
    static let shared = ContextualTipQueueCenter10876()
    @Published private(set) var state = ContextualTipQueue10876()

    func isGranted(_ anchor: UUID) -> Bool { state.isGranted(anchor: anchor) }

    func arrive(_ anchor: UUID, tip: ContextualTipID10876) { update { $0.arrive(anchor: anchor, tip: tip) } }
    func request(_ anchor: UUID, tip: ContextualTipID10876) { update { $0.request(anchor: anchor, tip: tip) } }
    func decline(_ anchor: UUID) { update { $0.decline(anchor: anchor) } }
    func withdraw(_ anchor: UUID) { update { $0.withdraw(anchor: anchor) } }

    private func update(_ change: (inout ContextualTipQueue10876) -> Void) {
        var next = state
        change(&next)
        if next != state { state = next }
    }
}

// MARK: - Anchoring

/// Puts `tip` in a popover on the modified control while the control is usable,
/// the app is in front and past its launch grace, TipKit says the tip should
/// display, and no other tip holds the screen. `learned` invalidates the tip.
private struct ContextualTipAnchor10876<T: Tip>: ViewModifier {
    let kind: ContextualTipID10876
    let tip: T
    let usable: Bool
    let learned: Bool
    let arrowEdge: Edge
    @ObservedObject private var queue = ContextualTipQueueCenter10876.shared
    @Environment(\.scenePhase) private var scenePhase
    @State private var anchor = UUID()

    private var wantsTip: Bool {
        ContextualTips10876.isEnabledOnThisPlatform && usable && !learned && scenePhase == .active
    }

    func body(content: Content) -> some View {
        content
            // A clear stand-in carries the popover, so a grant arriving or
            // leaving never changes the control's own identity (the chart's
            // touch surface and the bookmark's alert keep their state). It is
            // the control's size, so the arrow points at the control.
            .background {
                if queue.isGranted(anchor) {
                    Color.clear.popoverTip(tip, arrowEdge: arrowEdge)
                }
            }
            .task(id: learned) {
                guard learned, ContextualTips10876.isEnabledOnThisPlatform else { return }
                ContextualTips10876.configureIfNeeded()
                tip.invalidate(reason: .actionPerformed)
            }
            .task(id: wantsTip) {
                guard wantsTip else {
                    queue.withdraw(anchor)
                    return
                }
                ContextualTips10876.configureIfNeeded()
                queue.arrive(anchor, tip: kind)
                let wait = ContextualTipEligibility10876.delayBeforeAsking(
                    processAge: ContextualTips10876.processAge())
                try? await Task.sleep(for: .seconds(wait))
                guard !Task.isCancelled else { return }
                guard ContextualTipEligibility10876.appCanShowTips(
                    sceneIsActive: scenePhase == .active,
                    processAge: ContextualTips10876.processAge()) else {
                    queue.decline(anchor)
                    return
                }
                for await shouldDisplay in tip.shouldDisplayUpdates {
                    if Task.isCancelled { break }
                    if shouldDisplay {
                        queue.request(anchor, tip: kind)
                    } else {
                        queue.decline(anchor)
                    }
                }
            }
            .onDisappear { queue.withdraw(anchor) }
    }
}

/// Donates one pin engagement after `pinDwell` seconds on a detail page.
private struct PinEngagement10876: ViewModifier {
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        content.task(id: scenePhase == .active) {
            guard ContextualTips10876.isEnabledOnThisPlatform, scenePhase == .active else { return }
            try? await Task.sleep(for: .seconds(ContextualTipEligibility10876.pinDwell))
            guard !Task.isCancelled else { return }
            ContextualTips10876.configureIfNeeded()
            await PinTip10876.engaged.donate()
        }
    }
}

extension View {
    /// The bookmark on an event or market page. List and card bookmarks pass
    /// `isDetailAnchor: false` and get neither the tip nor the engagement count.
    @ViewBuilder
    func pinTip10876(isDetailAnchor: Bool, usable: Bool, learned: Bool) -> some View {
        if isDetailAnchor && ContextualTips10876.isEnabledOnThisPlatform {
            modifier(PinEngagement10876())
                .modifier(ContextualTipAnchor10876(
                    kind: .pin, tip: PinTip10876(),
                    usable: usable, learned: learned, arrowEdge: .top))
        } else {
            self
        }
    }

    func followLiveTip10876(game: String, usable: Bool, learned: Bool) -> some View {
        modifier(ContextualTipAnchor10876(
            kind: .followLive, tip: FollowLiveTip10876(game: game),
            usable: usable, learned: learned, arrowEdge: .top))
    }

    /// The inline game chart. `touchSurfaceInstalled` is the chart's own
    /// `chartScrubSurfaces` — no touch surface, nothing to teach.
    func exploreChartTip10876(touchSurfaceInstalled: Bool, dataPoints: [ChartDataPoint]) -> some View {
        modifier(ExploreChartTipAnchor10876(touchSurfaceInstalled: touchSurfaceInstalled,
                                            dataPoints: dataPoints))
    }
}

/// Reads VoiceOver itself so the chart gains no environment of its own, and
/// only walks the points when a touch surface could be taught at all.
private struct ExploreChartTipAnchor10876: ViewModifier {
    let touchSurfaceInstalled: Bool
    let dataPoints: [ChartDataPoint]
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOverRunning

    private var usable: Bool {
        guard ContextualTips10876.isEnabledOnThisPlatform, touchSurfaceInstalled, !voiceOverRunning else {
            return false
        }
        let primary = OddsChartView.primarySource(in: dataPoints)
        return ContextualTipEligibility10876.exploreChartUsable(
            touchSurfaceInstalled: touchSurfaceInstalled, voiceOverRunning: voiceOverRunning,
            primaryLineDates: dataPoints.filter { $0.source == primary }.map(\.date))
    }

    /// Arrow on top: the popover opens BELOW the chart, so the hero's subject,
    /// score and probability above it stay uncovered.
    func body(content: Content) -> some View {
        content.modifier(ContextualTipAnchor10876(
            kind: .exploreChart, tip: ExploreChartTip10876(),
            usable: usable, learned: false, arrowEdge: .top))
    }
}
