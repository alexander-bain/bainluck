import Combine
import os
import SwiftUI
import TipKit
import UserNotifications

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
/// * `ContextualTipHeroGate10876` — whether the page can take a tip: none
///   opens while the page's hero is on screen (`heroClearOfTips`).
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

    /// `ContextualTipEligibility10876.notificationPromptSettled`, read live.
    static func notificationPromptSettled() async -> Bool {
        let suppressed = !NotificationManager.shouldRequestPermission()
        if suppressed {
            return ContextualTipEligibility10876.notificationPromptSettled(
                authorizationIsNotDetermined: true, promptSuppressed: true)
        }
        let status = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        return ContextualTipEligibility10876.notificationPromptSettled(
            authorizationIsNotDetermined: status == .notDetermined, promptSuppressed: false)
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

    /// Called at the end of every chart gesture that read a moment; writes
    /// once per process. Logged, because case v6 (R1) saw a hidden-launch
    /// scrub leave the chart tip eligible on the next launch and nothing on
    /// screen can say whether this ran.
    static func chartLearned() {
        guard isEnabledOnThisPlatform, !chartLearnedThisProcess else { return }
        chartLearnedThisProcess = true
        configureIfNeeded()
        ExploreChartTip10876().invalidate(reason: .actionPerformed)
        logger.notice("chart tip invalidated: a scrub read a moment")
    }
}

extension PinManager {
    /// The pin store as the pin tip reads it. Here, not in `PinButton`: the
    /// limit is read only to decide the tip, never the tap.
    func pinTipReading10876(type: String, id: Int) -> PinTipStoreReading10876 {
        PinTipStoreReading10876(
            isPinned: isPinned(type: type, id: id), isSaving: isSaving(type: type, id: id),
            canPin: canPin(type: type), loadState: loadState,
            hasPinMessage: feedback != nil, savedPinCount: savedPins.count)
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
    func park(_ anchor: UUID, tip: ContextualTipID10876) { update { $0.park(anchor: anchor, tip: tip) } }
    func pageCannotShow(_ anchor: UUID, tip: ContextualTipID10876) {
        update { $0.pageCannotShow(anchor: anchor, tip: tip) }
    }
    func decline(_ anchor: UUID) { update { $0.decline(anchor: anchor) } }
    func withdraw(_ anchor: UUID) { update { $0.withdraw(anchor: anchor) } }

    private func update(_ change: (inout ContextualTipQueue10876) -> Void) {
        var next = state
        change(&next)
        guard next != state else { return }
        if next.holder?.anchor != state.holder?.anchor {
            let granted = next.holder.map { "\($0.tip)" } ?? "none"
            logger.notice("tip on screen: \(granted, privacy: .public)")
        }
        state = next
    }
}

// MARK: - The hero no tip may cover

/// Which detail pages have their hero scrolled wholly out of view, keyed like
/// the bookmark (`type:id`). The page's hero reports here; the bookmark in its
/// bar and the game chart read it — a toolbar item cannot see the scroll view
/// it sits over, and the chart is a sibling of the hero. A page that never
/// reports is never in the set, so its tips stay off.
@MainActor final class ContextualTipHeroGate10876: ObservableObject {
    static let shared = ContextualTipHeroGate10876()
    @Published private(set) var clear: Set<String> = []

    static func key(type: String, id: Int) -> String { "\(type):\(id)" }

    func isClear(type: String, id: Int) -> Bool { clear.contains(Self.key(type: type, id: id)) }

    func set(type: String, id: Int, clear isClear: Bool) {
        let key = Self.key(type: type, id: id)
        if isClear { clear.insert(key) } else { clear.remove(key) }
    }
}

/// On the page's hero: reports `heroClearOfTips` only when it flips, so a
/// scroll re-runs no page body (#8651). Measured in the page's own named
/// scroll space — the coordinate space set on the ScrollView itself, the form
/// the event page's bar title has used since #8320. R2 measured in the system
/// `.scrollView` space and the market page never cleared with its hero 1,000 pt
/// gone (case v6, D2). Each flip is logged, so a run can read the gate.
private struct ContextualTipHeroReporter10876: ViewModifier {
    let type: String
    let id: Int
    let scrollSpace: String

    func body(content: Content) -> some View {
        content
            .onGeometryChange(for: Bool.self) { proxy in
                ContextualTipEligibility10876.heroClearOfTips(heroBottom: proxy.frame(in: .named(scrollSpace)).maxY)
            } action: { isClear in
                logger.notice("hero \(type, privacy: .public):\(id, privacy: .public) clear=\(isClear, privacy: .public)")
                ContextualTipHeroGate10876.shared.set(type: type, id: id, clear: isClear)
            }
            .onDisappear { ContextualTipHeroGate10876.shared.set(type: type, id: id, clear: false) }
    }
}

// MARK: - The tips' own style

/// #10876 R2 — at AX3 the system style cut the pin tip's last line off inside
/// its own popover, over the hero's "Current win chance" (native's combined v3,
/// C-3b). The same parts as the system style — icon, title, message, close —
/// with the text given its full height. At accessibility sizes the icon sits
/// above the text, as the system's did, so the words keep the width.
struct ContextualTipStyle10876: TipViewStyle {
    func makeBody(configuration: Configuration) -> some View {
        ContextualTipBody10876(configuration: configuration)
    }
}

private struct ContextualTipBody10876: View {
    let configuration: TipViewStyle.Configuration
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        HStack(alignment: .top, spacing: 4) {
            layout {
                if let image = configuration.image {
                    image
                        .font(.title2)
                        .foregroundStyle(.tint)
                        .accessibilityHidden(true)
                }
                VStack(alignment: .leading, spacing: 4) {
                    if let title = configuration.title {
                        title.font(.headline)
                    }
                    if let message = configuration.message {
                        message.font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button {
                configuration.tip.invalidate(reason: .tipClosed)
            } label: {
                Image(systemName: "xmark")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Close")
            .padding(.top, -10)
            .padding(.trailing, -10)
        }
        .padding(16)
    }
}

// MARK: - Anchoring

/// Puts `tip` in a popover on the modified control while the control is usable,
/// the page can take it (`presentable`: its hero is out of view), the app is in
/// front with no permission alert still to come, TipKit says the tip should
/// display, and no other tip holds the screen. `learned` invalidates the tip.
///
/// A usable control on a page that cannot take its tip yet stays in the queue:
/// it parks once TipKit says the tip would display, so a lower tip cannot take
/// the session from it (case v6, D1), and a granted tip parks the moment the
/// hero comes back. Becoming presentable restarts the settle delay, so a tip
/// never lands mid-scroll.
private struct ContextualTipAnchor10876<T: Tip>: ViewModifier {
    let kind: ContextualTipID10876
    let tip: T
    let usable: Bool
    let presentable: Bool
    let learned: Bool
    let arrowEdge: Edge
    @ObservedObject private var queue = ContextualTipQueueCenter10876.shared
    @Environment(\.scenePhase) private var scenePhase
    @State private var anchor = UUID()

    private var wantsTip: Bool {
        ContextualTips10876.isEnabledOnThisPlatform && usable && !learned && scenePhase == .active
    }

    private struct Ask: Equatable {
        let wantsTip: Bool
        let presentable: Bool
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
                        .tipViewStyle(ContextualTipStyle10876())
                }
            }
            .task(id: learned) {
                guard learned, ContextualTips10876.isEnabledOnThisPlatform else { return }
                ContextualTips10876.configureIfNeeded()
                tip.invalidate(reason: .actionPerformed)
            }
            .task(id: Ask(wantsTip: wantsTip, presentable: presentable)) {
                guard wantsTip else {
                    queue.withdraw(anchor)
                    return
                }
                ContextualTips10876.configureIfNeeded()
                if presentable {
                    queue.arrive(anchor, tip: kind)
                } else {
                    queue.pageCannotShow(anchor, tip: kind)
                }
                try? await Task.sleep(for: .seconds(ContextualTipEligibility10876.settleDelay))
                guard !Task.isCancelled else { return }
                let promptSettled = await ContextualTips10876.notificationPromptSettled()
                guard !Task.isCancelled else { return }
                guard ContextualTipEligibility10876.appCanShowTips(
                    sceneIsActive: scenePhase == .active,
                    notificationPromptSettled: promptSettled) else {
                    queue.decline(anchor)
                    return
                }
                for await shouldDisplay in tip.shouldDisplayUpdates {
                    if Task.isCancelled { break }
                    if shouldDisplay && presentable {
                        queue.request(anchor, tip: kind)
                    } else if shouldDisplay {
                        queue.park(anchor, tip: kind)
                    } else {
                        queue.decline(anchor)
                    }
                }
            }
            .onDisappear { queue.withdraw(anchor) }
    }
}

/// Donates at most one pin engagement per mounted detail page, after
/// `pinDwell` seconds of foreground time on it (`PinDwell10876`).
private struct PinEngagement10876: ViewModifier {
    @Environment(\.scenePhase) private var scenePhase
    @State private var dwell = PinDwell10876()

    func body(content: Content) -> some View {
        content
            .task(id: scenePhase == .active) {
                guard ContextualTips10876.isEnabledOnThisPlatform else { return }
                dwell.sceneChanged(isActive: scenePhase == .active, now: Date())
                guard let due = dwell.dueDate else { return }
                try? await Task.sleep(for: .seconds(max(0, due.timeIntervalSinceNow)))
                guard !Task.isCancelled, dwell.donateIfDue(now: Date()) else { return }
                ContextualTips10876.configureIfNeeded()
                await PinTip10876.engaged.donate()
            }
            // Off screen stops the clock (a return starts a fresh 10 s) but
            // keeps `donated`: a sheet or pushed page and back is one visit.
            .onDisappear { dwell.sceneChanged(isActive: false, now: Date()) }
    }
}

extension View {
    /// The bookmark on an event or market page. List and card bookmarks pass
    /// `isDetailAnchor: false` and get neither the tip, the engagement count
    /// nor a read of the pin store. `localPinUIShowing` is the button's own
    /// limit alert or Manage pins sheet.
    @ViewBuilder
    func pinTip10876(isDetailAnchor: Bool, pinManager: PinManager, type: String, id: Int,
                     localPinUIShowing: Bool) -> some View {
        if isDetailAnchor && ContextualTips10876.isEnabledOnThisPlatform {
            modifier(PinEngagement10876())
                .modifier(PinTipAnchor10876(pinManager: pinManager, type: type, id: id,
                                            localPinUIShowing: localPinUIShowing))
        } else {
            self
        }
    }

    /// On a detail page's hero, keyed like that page's bookmark: lets the
    /// page's tips open only once the hero is out of view (`heroClearOfTips`).
    /// `scrollSpace` names the coordinate space set on the page's ScrollView.
    @ViewBuilder
    func contextualTipHero10876(type: String, id: Int, scrollSpace: String) -> some View {
        if ContextualTips10876.isEnabledOnThisPlatform {
            modifier(ContextualTipHeroReporter10876(type: type, id: id, scrollSpace: scrollSpace))
        } else {
            self
        }
    }

    /// Start Live Activity sits under the game chart, so with the hero on
    /// screen it is low on the page and its popover would flip up onto the
    /// hero, as the chart tip's did (C-3a). ux's own v7 run on a live game
    /// (15330832) saw it open 3 s after load with the hero on screen. It waits
    /// for the event page's hero like the others; `eventId` keys that gate.
    func followLiveTip10876(eventId: Int, game: String, usable: Bool, learned: Bool) -> some View {
        modifier(FollowLiveTipAnchor10876(eventId: eventId, game: game, usable: usable, learned: learned))
    }

    /// The inline game chart. `touchSurfaceInstalled` is the chart's own
    /// `chartScrubSurfaces` — no touch surface, nothing to teach. `eventId`
    /// keys the event page's hero gate; a chart whose id is not the page's
    /// never clears it, so its tip stays off (fails closed).
    func exploreChartTip10876(eventId: Int, touchSurfaceInstalled: Bool, dataPoints: [ChartDataPoint]) -> some View {
        modifier(ExploreChartTipAnchor10876(eventId: eventId, touchSurfaceInstalled: touchSurfaceInstalled,
                                            dataPoints: dataPoints))
    }
}

/// The detail bookmark's tip. Watches the hero gate, so the tip waits for the
/// hero to leave and leaves the moment the reader scrolls the hero back.
private struct PinTipAnchor10876: ViewModifier {
    @ObservedObject var pinManager: PinManager
    let type: String
    let id: Int
    let localPinUIShowing: Bool
    @ObservedObject private var heroes = ContextualTipHeroGate10876.shared

    func body(content: Content) -> some View {
        let state = ContextualTipEligibility10876.pinTip(
            isDetailAnchor: true, localPinUIShowing: localPinUIShowing,
            read: { pinManager.pinTipReading10876(type: type, id: id) })
        content.modifier(ContextualTipAnchor10876(
            kind: .pin, tip: PinTip10876(),
            usable: state.usable, presentable: heroes.isClear(type: type, id: id),
            learned: state.learned, arrowEdge: .top))
    }
}

/// Whether a control inside the page is at least half on screen in its
/// scroll view (iOS 18+). Not yet reported reads false, so its tip waits.
/// iOS 17 has no visibility signal: it reports on screen once it appears and
/// keeps the hero rule alone. Each flip is logged.
private struct PageControlOnScreen10876: ViewModifier {
    let kind: ContextualTipID10876
    @Binding var onScreen: Bool

    func body(content: Content) -> some View {
        if #available(iOS 18.0, macOS 15.0, visionOS 2.0, *) {
            content.onScrollVisibilityChange(threshold: 0.5) { visible in
                logger.notice("control \(String(describing: kind), privacy: .public) onScreen=\(visible, privacy: .public)")
                onScreen = visible
            }
        } else {
            content.onAppear { onScreen = true }
        }
    }
}

/// Start Live Activity's tip. Watches the event page's hero gate and needs
/// the control itself on screen.
private struct FollowLiveTipAnchor10876: ViewModifier {
    let eventId: Int
    let game: String
    let usable: Bool
    let learned: Bool
    @ObservedObject private var heroes = ContextualTipHeroGate10876.shared
    @State private var onScreen = false

    func body(content: Content) -> some View {
        content
            .modifier(PageControlOnScreen10876(kind: .followLive, onScreen: $onScreen))
            .modifier(ContextualTipAnchor10876(
                kind: .followLive, tip: FollowLiveTip10876(game: game),
                usable: usable,
                presentable: ContextualTipEligibility10876.pageControlPresentable(
                    heroClear: heroes.isClear(type: "event", id: eventId), controlOnScreen: onScreen),
                learned: learned, arrowEdge: .top))
    }
}

/// Reads VoiceOver itself so the chart gains no environment of its own, and
/// only walks the points when a touch surface could be taught at all.
private struct ExploreChartTipAnchor10876: ViewModifier {
    let eventId: Int
    let touchSurfaceInstalled: Bool
    let dataPoints: [ChartDataPoint]
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOverRunning
    @ObservedObject private var heroes = ContextualTipHeroGate10876.shared
    @State private var onScreen = false

    private var usable: Bool {
        guard ContextualTips10876.isEnabledOnThisPlatform, touchSurfaceInstalled, !voiceOverRunning else {
            return false
        }
        let primary = OddsChartView.primarySource(in: dataPoints)
        return ContextualTipEligibility10876.exploreChartUsable(
            touchSurfaceInstalled: touchSurfaceInstalled, voiceOverRunning: voiceOverRunning,
            primaryLineDates: dataPoints.filter { $0.source == primary }.map(\.date))
    }

    /// Arrow on top asks for the popover BELOW the chart, but the system
    /// flips it above when the chart sits low on the screen (case v6, C-3a),
    /// so it also waits for the event page's hero to leave: by then the chart
    /// is near the top and there is no hero left to cover. It also needs the
    /// chart itself on screen (`pageControlPresentable`).
    func body(content: Content) -> some View {
        content
            .modifier(PageControlOnScreen10876(kind: .exploreChart, onScreen: $onScreen))
            .modifier(ContextualTipAnchor10876(
                kind: .exploreChart, tip: ExploreChartTip10876(),
                usable: usable,
                presentable: ContextualTipEligibility10876.pageControlPresentable(
                    heroClear: heroes.isClear(type: "event", id: eventId), controlOnScreen: onScreen),
                learned: false, arrowEdge: .top))
    }
}
