import Foundation

/// #10876 — the three contextual tips, in the order one waits for another.
///
/// Following a live game outranks the others because it is only true while the
/// game is live; pinning and the chart are still true tomorrow.
nonisolated enum ContextualTipID10876: Int, CaseIterable, Comparable, Sendable {
    case followLive = 0
    case pin = 1
    case exploreChart = 2

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }
}

/// #10876 — one tip on screen at a time, and one KIND of tip per app session.
///
/// TipKit's daily display frequency already spaces new tips out; this is the
/// page-level half it does not cover: the event page mounts all three anchors
/// at once, and a tip left open yesterday is still eligible today.
///
/// An anchor ARRIVES when its control becomes usable, then — after its settle
/// delay — either REQUESTS (TipKit says its tip should display) or DECLINES.
/// An anchor whose tip TipKit would display but whose page cannot take it yet
/// (the hero is still on screen) PARKS instead of requesting. The best
/// requester is granted only once no higher-priority anchor on screen is still
/// undecided or parked, so priority holds even though anchors decide at
/// slightly different moments, and a tip waiting only on the page never hands
/// the session to a lower one (native's case v6, D1). A grant is sticky until its anchor withdraws: a
/// higher-priority tip arriving later never yanks one the reader is looking
/// at. Once a kind has been granted, only that kind may be granted again this
/// session (it can reappear on its own control; a different tip waits for the
/// next launch).
nonisolated struct ContextualTipQueue10876: Equatable, Sendable {
    nonisolated enum Phase: Equatable, Sendable { case undecided, requesting, parked, declined }

    nonisolated struct Entry: Equatable, Sendable {
        let anchor: UUID
        let tip: ContextualTipID10876
        let order: Int
        var phase: Phase
    }

    private(set) var holder: Entry?
    private(set) var sessionTip: ContextualTipID10876?
    private var entries: [Entry] = []
    private var nextOrder = 0

    func isGranted(anchor: UUID) -> Bool { holder?.anchor == anchor }

    /// The control is usable; its tip has not been asked about yet.
    mutating func arrive(anchor: UUID, tip: ContextualTipID10876) {
        guard holder?.anchor != anchor, !entries.contains(where: { $0.anchor == anchor }) else { return }
        entries.append(Entry(anchor: anchor, tip: tip, order: nextOrder, phase: .undecided))
        nextOrder += 1
    }

    mutating func request(anchor: UUID, tip: ContextualTipID10876) {
        guard holder?.anchor != anchor else { return }
        arrive(anchor: anchor, tip: tip)
        set(anchor, to: .requesting)
        promote()
    }

    /// TipKit would display the tip, but its page cannot take it yet. A tip on
    /// screen leaves it at once; the anchor keeps its place and still holds
    /// lower-priority tips back until it requests, declines or withdraws.
    mutating func park(anchor: UUID, tip: ContextualTipID10876) {
        if holder?.anchor == anchor {
            holder = nil
        }
        arrive(anchor: anchor, tip: tip)
        set(anchor, to: .parked)
        promote()
    }

    /// The page can no longer take the tip (the hero came back). A tip on
    /// screen or already requesting parks at once, before TipKit is asked
    /// again, so nothing is granted over the hero during the settle delay;
    /// any other anchor just arrives.
    mutating func pageCannotShow(anchor: UUID, tip: ContextualTipID10876) {
        let requesting = entries.contains { $0.anchor == anchor && $0.phase == .requesting }
        if holder?.anchor == anchor || requesting {
            park(anchor: anchor, tip: tip)
        } else {
            arrive(anchor: anchor, tip: tip)
        }
    }

    /// TipKit says no (rules unmet, invalidated, rate-limited). The anchor stays
    /// registered but no longer holds lower-priority tips back.
    mutating func decline(anchor: UUID) {
        if holder?.anchor == anchor {
            holder = nil
        }
        set(anchor, to: .declined)
        promote()
    }

    mutating func withdraw(anchor: UUID) {
        entries.removeAll { $0.anchor == anchor }
        if holder?.anchor == anchor {
            holder = nil
        }
        promote()
    }

    private mutating func set(_ anchor: UUID, to phase: Phase) {
        if let index = entries.firstIndex(where: { $0.anchor == anchor }) { entries[index].phase = phase }
    }

    private mutating func promote() {
        guard holder == nil else { return }
        let admissible = entries.filter { $0.phase == .requesting && (sessionTip == nil || $0.tip == sessionTip) }
        guard let best = admissible.min(by: { ($0.tip, $0.order) < ($1.tip, $1.order) }) else { return }
        let higherPending = entries.contains {
            ($0.phase == .undecided || $0.phase == .parked) && $0.tip < best.tip
                && (sessionTip == nil || $0.tip == sessionTip)
        }
        guard !higherPending else { return }
        entries.removeAll { $0.anchor == best.anchor }
        holder = best
        sessionTip = best.tip
    }
}

/// #10876 — when each tip's control is actually usable, and when its action is
/// already known. Pure, so every transition is a unit test rather than a render.
nonisolated enum ContextualTipEligibility10876 {
    /// A control must stay usable this long before its tip asks to appear, so a
    /// tip never lands on a page that is still loading or being scrolled past.
    static let settleDelay: TimeInterval = 3
    /// Seconds on one detail page that count as meaningful engagement with it.
    static let pinDwell: TimeInterval = 10
    /// The pin tip waits for this many engaged detail visits.
    static let pinEngagementsBeforeTip = 2
    /// The chart tip waits for at least this many distinct observed moments…
    static let chartMinimumMoments = 3
    /// …spanning at least this long, so there is something to scrub through.
    static let chartMinimumSpan: TimeInterval = 60

    /// No tip while the scene is inactive — a system alert or sheet (the
    /// notification permission alert, Sign in with Apple) is up — and none
    /// until the notification permission question has been answered or
    /// suppressed. `NotificationManager` asks 5 s after the root task's
    /// `loadPins()` returns, which for a signed-in reader is a server fetch of
    /// unknown length, so no launch-relative delay can promise to come after
    /// it. Answering the alert takes the scene inactive and back, which
    /// re-runs every anchor, so a tip held back here asks again then. If the
    /// request itself errors the status stays undetermined and tips stay off:
    /// fails closed.
    static func appCanShowTips(sceneIsActive: Bool, notificationPromptSettled: Bool) -> Bool {
        sceneIsActive && notificationPromptSettled
    }

    /// The permission alert can no longer appear: it was answered (any status
    /// but `.notDetermined`) or the launch argument suppresses the ask.
    static func notificationPromptSettled(authorizationIsNotDetermined: Bool, promptSuppressed: Bool) -> Bool {
        promptSuppressed || !authorizationIsNotDetermined
    }

    /// Pinning is only taught where a tap would actually pin: an unpinned
    /// subject, a free slot, no save in flight, a pin store that accepts adds,
    /// and no pin message, alert or sheet already on screen.
    static func pinUsable(isDetailAnchor: Bool, isPinned: Bool, isSaving: Bool, canPin: Bool,
                          pinLoadState: PinLoadState, isShowingPinMessage: Bool) -> Bool {
        isDetailAnchor && !isPinned && !isSaving && canPin && pinStoreAcceptsAdds(pinLoadState)
            && !isShowingPinMessage
    }

    /// `PinManager.togglePin` refuses every add on a signed-in account whose
    /// pins are not `.loaded` — still restoring OR failed — with "Refresh your
    /// saved pins". `.local` (signed out) has no account store to wait for.
    static func pinStoreAcceptsAdds(_ state: PinLoadState) -> Bool {
        switch state {
        case .local, .loaded: return true
        case .loading, .failed: return false
        }
    }

    /// A reader with anything pinned has already found the control.
    static func pinLearned(savedPinCount: Int) -> Bool { savedPinCount > 0 }

    /// The whole pin tip for one bookmark. A list or card bookmark is decided
    /// before `read` runs, so it never touches the pin store; a detail
    /// bookmark reads it once. Decided here so `PinButton` never reads the pin
    /// limit itself (#9495: the button must not pre-judge the limit).
    ///
    /// The hero is NOT a clause here. It decides whether the page can take the
    /// tip (`heroClearOfTips`), not whether the control is usable: a pin tip
    /// waiting only on the hero parks and keeps its priority (case v6, D1).
    static func pinTip(isDetailAnchor: Bool, localPinUIShowing: Bool,
                       read: () -> PinTipStoreReading10876) -> PinTipState10876 {
        guard isDetailAnchor else { return .off }
        let store = read()
        return PinTipState10876(
            usable: pinUsable(isDetailAnchor: true, isPinned: store.isPinned, isSaving: store.isSaving,
                             canPin: store.canPin, pinLoadState: store.loadState,
                             isShowingPinMessage: store.hasPinMessage || localPinUIShowing),
            learned: pinLearned(savedPinCount: store.savedPinCount))
    }

    /// No tip opens while any of the page's hero is on screen. The pin tip
    /// opens from the bar straight down over the top of the page (native's
    /// combined v3, B-3b and A-3: over the win chance and both crests). The
    /// chart tip, with the chart low on the screen, flips above it onto the
    /// hero (case v6, C-3a at AX3: under "Current win chance", over the team
    /// rows, eating the swipes). Start Live Activity sits under the chart, so
    /// its tip waits too. So all three wait until the hero has scrolled
    /// wholly out of its scroll view — `heroBottom` in the scroll view's own
    /// named space, the one the event page's bar title already measures in
    /// (#8320), ≤ 0 — and leave the moment any of it comes back. Not measured
    /// (`nil`) keeps them off.
    static func heroClearOfTips(heroBottom: CGFloat?) -> Bool {
        guard let heroBottom else { return false }
        return heroBottom <= 0
    }

    /// A tip anchored IN the page (the chart, Start Live Activity) also needs
    /// its own control on screen: once the hero is out, one swipe can carry
    /// the chart off the top too (ux's v7 testA frame), and a popover granted
    /// then points at nothing. The bookmark is in the bar and always on screen.
    static func pageControlPresentable(heroClear: Bool, controlOnScreen: Bool) -> Bool {
        heroClear && controlOnScreen
    }

    /// Taught only where Start Live Activity is shown AND tappable on a game
    /// that is live now — never for a held, disabled or unsupported control.
    static func followLiveUsable(controlShown: Bool, activitiesEnabled: Bool, gameIsLive: Bool,
                                 isBusy: Bool, activeActivityCount: Int, sceneIsActive: Bool) -> Bool {
        controlShown && activitiesEnabled && gameIsLive && !isBusy
            && activeActivityCount == 0 && sceneIsActive
    }

    /// Any running Live Activity means the reader has used the control.
    static func followLiveLearned(activeActivityCount: Int) -> Bool { activeActivityCount > 0 }

    /// The chart's hold-and-slide is a touch gesture: taught only where the
    /// touch surface is installed, never to VoiceOver (which reads the chart
    /// through its accessibility value), and only over a line worth exploring.
    static func exploreChartUsable(touchSurfaceInstalled: Bool, voiceOverRunning: Bool,
                                   primaryLineDates: [Date]) -> Bool {
        touchSurfaceInstalled && !voiceOverRunning && chartHasUsefulData(primaryLineDates)
    }

    static func chartHasUsefulData(_ dates: [Date]) -> Bool {
        let moments = Set(dates)
        guard moments.count >= chartMinimumMoments,
              let first = moments.min(), let last = moments.max() else { return false }
        return last.timeIntervalSince(first) >= chartMinimumSpan
    }
}

/// What the pin tip reads from the pin store for one subject.
nonisolated struct PinTipStoreReading10876: Equatable, Sendable {
    var isPinned: Bool
    var isSaving: Bool
    var canPin: Bool
    var loadState: PinLoadState
    var hasPinMessage: Bool
    var savedPinCount: Int
}

nonisolated struct PinTipState10876: Equatable, Sendable {
    var usable: Bool
    var learned: Bool
    static let off = PinTipState10876(usable: false, learned: false)
}

/// #10876 — one pin engagement per mounted detail page: the first `pinDwell`
/// seconds of continuous on-screen, foreground time on it. Leaving the
/// foreground or the screen restarts the clock; once donated, nothing on this
/// page donates again — the notification alert or a trip to the background must
/// not turn one visit into the two the pin rule waits for.
nonisolated struct PinDwell10876: Equatable, Sendable {
    private(set) var activeSince: Date?
    private(set) var donated = false

    mutating func sceneChanged(isActive: Bool, now: Date) {
        if !isActive {
            activeSince = nil
        } else if activeSince == nil {
            activeSince = now
        }
    }

    /// When the dwell in progress completes; `nil` once donated or while the
    /// scene is not active.
    var dueDate: Date? {
        guard !donated, let activeSince else { return nil }
        return activeSince.addingTimeInterval(ContextualTipEligibility10876.pinDwell)
    }

    /// True at most once per page, when a dwell has completed.
    mutating func donateIfDue(now: Date) -> Bool {
        guard let dueDate, now >= dueDate else { return false }
        donated = true
        return true
    }
}

/// #10876 — the test-only switch, read like `LaunchRig` reads its arguments:
/// `-contextual_tips_10876 reset` starts this launch as a fresh reader (TipKit's
/// own datastore only — pins, consent and every other preference are
/// untouched); `-contextual_tips_10876 hidden` keeps every tip off screen for
/// journeys that must not be interrupted. A reader who passes nothing gets
/// `.normal`, and nothing here can change what they see.
nonisolated enum ContextualTipLaunchOption10876: Equatable, Sendable {
    case normal, reset, hidden

    static let key = "contextual_tips_10876"

    static func read(defaults: UserDefaults = .standard) -> Self {
        switch defaults.string(forKey: key)?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "reset": return .reset
        case "hidden": return .hidden
        default: return .normal
        }
    }
}
