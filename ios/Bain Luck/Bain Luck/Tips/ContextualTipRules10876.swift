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
/// The best requester is granted only once no higher-priority anchor on screen
/// is still undecided, so priority holds even though anchors decide at
/// slightly different moments. A grant is sticky until its anchor withdraws: a
/// higher-priority tip arriving later never yanks one the reader is looking
/// at. Once a kind has been granted, only that kind may be granted again this
/// session (it can reappear on its own control; a different tip waits for the
/// next launch).
nonisolated struct ContextualTipQueue10876: Equatable, Sendable {
    nonisolated enum Phase: Equatable, Sendable { case undecided, requesting, declined }

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
        let higherUndecided = entries.contains {
            $0.phase == .undecided && $0.tip < best.tip && (sessionTip == nil || $0.tip == sessionTip)
        }
        guard !higherUndecided else { return }
        entries.removeAll { $0.anchor == best.anchor }
        holder = best
        sessionTip = best.tip
    }
}

/// #10876 — when each tip's control is actually usable, and when its action is
/// already known. Pure, so every transition is a unit test rather than a render.
nonisolated enum ContextualTipEligibility10876 {
    /// No tip in the first seconds of a cold launch. `NotificationManager` asks
    /// for notification permission 5 s after the root task starts; a popover
    /// opened just before that system alert would compete with it. While the
    /// alert (or any system sheet, such as Sign in with Apple) is up the scene
    /// is inactive, which `appCanShowTips` refuses separately.
    static let launchGrace: TimeInterval = 20
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

    static func appCanShowTips(sceneIsActive: Bool, processAge: TimeInterval) -> Bool {
        sceneIsActive && processAge >= launchGrace
    }

    /// How long an anchor waits before asking: the settle delay, stretched to
    /// the end of the launch grace on a fresh process.
    static func delayBeforeAsking(processAge: TimeInterval) -> TimeInterval {
        max(settleDelay, launchGrace - processAge)
    }

    /// Pinning is only taught where a tap would actually pin: an unpinned
    /// subject, a free slot, no save in flight, an account store that is not
    /// mid-restore, and no pin message, alert or sheet already on screen.
    static func pinUsable(isDetailAnchor: Bool, isPinned: Bool, isSaving: Bool, canPin: Bool,
                          pinStoreIsLoading: Bool, isShowingPinMessage: Bool) -> Bool {
        isDetailAnchor && !isPinned && !isSaving && canPin && !pinStoreIsLoading && !isShowingPinMessage
    }

    /// A reader with anything pinned has already found the control.
    static func pinLearned(savedPinCount: Int) -> Bool { savedPinCount > 0 }

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

/// #10876 — how long this process has been running, from the kernel's record
/// of its start, so the launch grace holds no matter when the first anchor
/// appears. `nil` if the kernel will not say; callers then fall back to the
/// first time they asked.
nonisolated enum ProcessAge10876 {
    static func startDate() -> Date? {
        var info = kinfo_proc()
        var size = MemoryLayout<kinfo_proc>.stride
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()]
        guard sysctl(&mib, u_int(mib.count), &info, &size, nil, 0) == 0, size > 0 else { return nil }
        let started = info.kp_proc.p_un.__p_starttime
        guard started.tv_sec > 0 else { return nil }
        return Date(timeIntervalSince1970: TimeInterval(started.tv_sec) + TimeInterval(started.tv_usec) / 1_000_000)
    }
}
