import Foundation
import SwiftUI

#if canImport(UIKit)
import UIKit
#endif

/// SCREEN TIMING — the felt number, on native, in the same shape as the web.
///
/// WHAT THIS IS FOR. Alex's question is "how long does a stranger wait before
/// they can see a real card", and until now nobody could answer it for the app
/// at all: the existing native latency rails (`discover_feed_first_render`,
/// `sports_feed_first_render`, `my_stuff_first_render`) are three bespoke
/// packets for three screens, with three different parameter sets, and every
/// other screen — event detail, search, tournaments, categories, calibration,
/// the whole Watch app — reports nothing. There is no way to build a per-screen
/// table out of that, which is exactly what the charter asks for.
///
/// 🔴 THE PACKET IS DELIBERATELY IDENTICAL TO THE WEB'S. Same event name
/// (`screen_timing`), same parameter names, same units, same `-1` convention.
/// `frontend/lib/screenTiming.ts` is the other half. They must stay in step or
/// the promised single table becomes two tables that have to be reconciled by
/// hand — which is the state this queue exists to end.
///
/// WHAT COUNTS AS "FIRST REAL CARD" ON NATIVE. The web can detect it from the
/// DOM; SwiftUI has no equivalent, so a screen DECLARES it by attaching
/// `.firstRealCard()` to the first row/card it renders with real content. That
/// is a two-word change per screen and it is the only per-screen work this rail
/// requires. A screen that forgets it reports `outcome_class == "no_card"`
/// rather than reporting nothing — the missing rows stay visible.
///
/// 🔴 A SKELETON MUST NOT CARRY THE MARKER. The whole point of the number is
/// that it excludes placeholders. `.firstRealCard()` on a redacted/shimmering
/// placeholder would report the app as instant and be worse than no rail at all.
/// `ScreenTimingRecorder.markFirstCard` therefore ignores marks taken while the
/// screen has declared itself loading (`markLoading(true)`).
public struct ScreenTimingPacket: Equatable, Sendable {
    /// Bounded screen slug — "discover", "sports", "event_detail". Never an id.
    public let surface: String
    /// "cold" = first screen after a process launch. "warm" = in-app navigation.
    public let entry: String
    public let shellMs: Int
    public let firstCardMs: Int
    public let foldMs: Int
    public let interactiveMs: Int
    public let cardCount: Int
    public let deviceClass: String
    public let networkClass: String
    public let appBuild: String
    public let outcomeClass: String

    /// The exact wire form. Keys match the web packet character for character;
    /// `AnalyticsPrivacy` drops anything not on its allowlist, so a typo here is
    /// a silently missing column rather than a visible error — hence the guard
    /// test that asserts these keys against the allowlist.
    public var parameters: [String: Any] {
        [
            "surface": surface,
            "entry": entry,
            "shell_ms": shellMs,
            "first_card_ms": firstCardMs,
            "fold_ms": foldMs,
            "interactive_ms": interactiveMs,
            "card_count": cardCount,
            "device_class": deviceClass,
            "network_class": networkClass,
            "app_build": appBuild,
            "outcome_class": outcomeClass,
        ]
    }
}

public extension ScreenTimingPacket {
    /// Build a packet from a screen that already knows its own first-render
    /// moment — the three shipped native rails do, and bridging them is how the
    /// main tabs get a row in the table on day one without touching a view.
    ///
    /// `foldMs` / `interactiveMs` are `-1` here on purpose: those call sites
    /// genuinely do not know when the first screen stopped changing, and
    /// inventing the value by copying `firstCardMs` would put a fabricated
    /// number in a column the target is judged on.
    ///
    /// 🔴 `entry` IS REQUIRED, and that is the whole point of it being required
    /// (CERT-782). It used to default to `ScreenTimingSession.nextEntry()`, which
    /// is evaluated at the CALL site — and this factory is called at the moment
    /// the first card finally renders. A cold launch whose first card took 21 s
    /// therefore fell outside the 20 s cold window and was filed as `warm`: the
    /// slowest cold rows deleted themselves from the cold cohort, in the
    /// flattering direction, silently. The label now comes from the screen's ARM
    /// (`ScreenTimingSession.armScreen`), taken when the reader entered the
    /// screen. Making the argument mandatory means the wrong moment is no longer
    /// expressible, rather than merely no longer used.
    static func bridged(
        surface: String,
        firstCardMs: Int,
        cardCount: Int,
        entry: String
    ) -> ScreenTimingPacket {
        ScreenTimingPacket(
            surface: surface,
            entry: entry,
            shellMs: screenTimingNotMeasured,
            firstCardMs: firstCardMs,
            foldMs: screenTimingNotMeasured,
            interactiveMs: screenTimingNotMeasured,
            cardCount: cardCount,
            deviceClass: ScreenTimingEnvironment.deviceClass,
            networkClass: ScreenTimingEnvironment.networkClass,
            appBuild: ScreenTimingEnvironment.appBuild,
            outcomeClass: cardCount > 0 ? "ok" : "empty"
        )
    }

    /// A screen that was entered and produced no card. `outcome` is the reason:
    /// `no_card` (the deadline expired with nothing on screen — a failure),
    /// `empty` (the screen legitimately had nothing to show), or `error`.
    ///
    /// Every timing column is `-1`, never `0`. A screen that rendered nothing
    /// rendered FAST, so a rail that put a small number here would report the
    /// worst experience on the board as the best one — the exact defect this
    /// packet exists to make visible.
    static func withoutCard(surface: String, entry: String, outcome: String) -> ScreenTimingPacket {
        ScreenTimingPacket(
            surface: surface,
            entry: entry,
            shellMs: screenTimingNotMeasured,
            firstCardMs: screenTimingNotMeasured,
            foldMs: screenTimingNotMeasured,
            interactiveMs: screenTimingNotMeasured,
            cardCount: 0,
            deviceClass: ScreenTimingEnvironment.deviceClass,
            networkClass: ScreenTimingEnvironment.networkClass,
            appBuild: ScreenTimingEnvironment.appBuild,
            outcomeClass: outcome
        )
    }
}

/// The bounded surface slugs the three bespoke first-render rails report under.
///
/// 🔴 These are constants and not literals because the arm and the report are in
/// DIFFERENT FILES. A view arming `"mystuff"` while `AnalyticsService` reports
/// `"my_stuff"` would not fail to build, would not fail a test, and would produce
/// a permanent stream of `no_card` rows for a tab that works — an instrument
/// lying in the UNflattering direction, which is just as useless.
public enum ScreenTimingSurface {
    public static let discover = "discover"
    public static let sports = "sports"
    public static let myStuff = "my_stuff"
    /// The surfaces whose first card is announced by a bespoke first-render rail
    /// rather than by a `.firstRealCard()` marker. Only these are armed: arming a
    /// screen that has no reporter would emit `no_card` forever and say "Browse
    /// never shows a card" when the truth is "Browse is not instrumented yet".
    public static let bridged = [discover, sports, myStuff]
}

/// Where a finished packet goes. A protocol so the recorder is testable without
/// Firebase, and so the Watch can substitute a store-and-forward sink.
public protocol ScreenTimingSink: Sendable {
    func send(_ packet: ScreenTimingPacket)
}

/// The production sink: the app's one analytics emission boundary.
public struct AnalyticsScreenTimingSink: ScreenTimingSink {
    public init() {}
    public func send(_ packet: ScreenTimingPacket) {
        AnalyticsService.log("screen_timing", packet.parameters)
    }
}

/// `-1` means "not measurable / did not happen" — never `0`, which is a real
/// and very different claim. Matches `NOT_MEASURED` on the web.
public let screenTimingNotMeasured = -1

// MARK: - Process launch clock

/// When this process started, used to separate a COLD launch from a warm
/// in-app navigation. Read once: `ProcessInfo.systemUptime` minus the process's
/// own elapsed time is not available portably, so the first touch of this file
/// is the reference. It is touched from `Bain_LuckApp.init()` in practice, which
/// is as close to launch as app code can get.
public enum AppLaunchClock {
    public static let start = Date()
    /// Seconds since launch. `touch()` exists so the app can force the lazy
    /// `start` to be evaluated at the earliest possible moment rather than at
    /// whichever screen happens to measure first.
    public static func touch() { _ = start }
    public static var elapsed: TimeInterval { Date().timeIntervalSince(start) }
}

// MARK: - Device + network classification

public enum ScreenTimingEnvironment {
    /// Coarse hardware class. Never a model string, never a fingerprint.
    ///
    /// iPad is separated from iPhone here on purpose: #2606 P3 records that the
    /// app reports `platform=ios` for both, so an iPad has been indistinguishable
    /// from an iPhone in every existing rail. A latency table that cannot tell a
    /// 13" iPad from an iPhone SE cannot act on either.
    public static var deviceClass: String {
        #if os(watchOS)
        return "watch"
        #elseif os(macOS)
        return "desktop"
        #elseif canImport(UIKit)
        switch UIDevice.current.userInterfaceIdiom {
        case .pad: return "tablet"
        case .phone: return "phone"
        case .mac: return "desktop"
        case .tv: return "desktop"
        default: return "unknown"
        }
        #else
        return "unknown"
        #endif
    }

    /// Coarse reachability label. Kept deliberately crude: the useful split is
    /// "was this a phone on a cell link", not a carrier or an SSID.
    public static var networkClass: String = "unknown"

    /// Short build identifier. A version+build string, never user data.
    public static var appBuild: String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return String("\(short)+\(build)".prefix(24))
    }
}

// MARK: - Recorder

/// One screen's measurement. Created on appear, finished when the screen settles
/// or its budget expires, cancelled if the reader leaves first.
///
/// `@MainActor` because every mark comes from a SwiftUI body/appear callback and
/// the marks must be ordered; the class itself does no async work.
@MainActor
public final class ScreenTimingRecorder {
    /// The screen is "settled" once no new above-the-fold card has arrived for
    /// this long. Same constant as the web rail.
    static let quietSeconds: TimeInterval = 1.5
    /// A screen that has shown no card by now reports `no_card` rather than
    /// nothing. The silent case is the expensive one: a screen that renders
    /// nothing renders FAST, so a timing-only rail reports its worst failure as
    /// its best result.
    static let budgetSeconds: TimeInterval = 30

    private let surface: String
    private let entry: String
    private let sink: ScreenTimingSink
    private let now: () -> Date
    private let origin: Date

    private var firstCardMs: Int?
    private var foldMs: Int?
    private var cardCount = 0
    private var shellMs: Int
    private var isLoading = false
    private var finished = false
    private var quietTask: Task<Void, Never>?
    private var budgetTask: Task<Void, Never>?

    public init(
        surface: String,
        entry: String,
        sink: ScreenTimingSink = AnalyticsScreenTimingSink(),
        now: @escaping () -> Date = Date.init,
        shellMs: Int = screenTimingNotMeasured,
        autoFinish: Bool = true
    ) {
        self.surface = surface
        self.entry = entry
        self.sink = sink
        self.now = now
        self.origin = now()
        self.shellMs = shellMs
        if autoFinish {
            budgetTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: UInt64(Self.budgetSeconds * 1_000_000_000))
                guard !Task.isCancelled else { return }
                self?.finish()
            }
        }
    }

    private var elapsedMs: Int { Int(((now().timeIntervalSince(origin)) * 1000).rounded()) }

    /// Declare that the screen is currently showing placeholders. A first-card
    /// mark taken while this is true is IGNORED — see the class note: a skeleton
    /// wearing the marker would report the app as instant.
    public func markLoading(_ loading: Bool) { isLoading = loading }

    /// The first real, non-placeholder card is on screen. Idempotent — a SwiftUI
    /// body can run many times and only the first mark is the measurement.
    public func markFirstCard() {
        guard !finished, !isLoading else { return }
        if firstCardMs == nil { firstCardMs = elapsedMs }
        cardCount += 1
        foldMs = elapsedMs
        armQuiet()
    }

    /// The screen finished its critical work and stopped changing under the
    /// reader. Optional: when a screen never calls it, `fold` stands in, exactly
    /// as on the web.
    public func markInteractive() {
        guard !finished else { return }
        foldMs = elapsedMs
        armQuiet()
    }

    /// The screen legitimately has nothing to show (an empty Profile, a search
    /// with no results). Distinct from `no_card`, which is a failure.
    public func markEmpty() { finish(outcome: "empty") }

    /// The screen failed to load its data.
    public func markError() { finish(outcome: "error") }

    private func armQuiet() {
        quietTask?.cancel()
        quietTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(Self.quietSeconds * 1_000_000_000))
            guard !Task.isCancelled else { return }
            self?.finish()
        }
    }

    /// Emit. Idempotent: the quiet timer, the budget timer and an explicit call
    /// all race, and exactly one packet must win.
    public func finish(outcome: String? = nil) {
        guard !finished else { return }
        finished = true
        quietTask?.cancel(); quietTask = nil
        budgetTask?.cancel(); budgetTask = nil
        let resolved = outcome ?? (firstCardMs == nil ? "no_card" : "ok")
        sink.send(ScreenTimingPacket(
            surface: surface,
            entry: entry,
            shellMs: shellMs,
            firstCardMs: firstCardMs ?? screenTimingNotMeasured,
            foldMs: foldMs ?? screenTimingNotMeasured,
            interactiveMs: foldMs ?? screenTimingNotMeasured,
            cardCount: cardCount,
            deviceClass: ScreenTimingEnvironment.deviceClass,
            networkClass: ScreenTimingEnvironment.networkClass,
            appBuild: ScreenTimingEnvironment.appBuild,
            outcomeClass: resolved
        ))
    }

    /// The reader left before the screen settled. Stop WITHOUT emitting: a
    /// partial measurement of an abandoned screen is reader impatience, not a
    /// slow screen, and reporting it as one poisons the p95.
    public func cancel() {
        finished = true
        quietTask?.cancel(); quietTask = nil
        budgetTask?.cancel(); budgetTask = nil
    }
}

// MARK: - Cold / warm, and the arm that keeps a blank screen in the table

/// How a screen's measurement is STARTED and how it is LABELLED, for the three
/// tabs whose first card is announced by a bespoke first-render rail instead of
/// by a `.firstRealCard()` marker.
///
/// 🔴 THIS EXISTS BECAUSE OF TWO DEFECTS CERT-782 FOUND IN THE FIRST CUT, and
/// both of them moved the number in the flattering direction.
///
///   1. **The label was taken at the wrong moment.** `nextEntry()` was evaluated
///      when the first card finally rendered. A cold launch whose first card
///      arrived after the 20 s cold window was therefore relabelled `warm` — the
///      slowest cold rows quietly leaving the cold cohort. The label is now
///      claimed at ARM time, when the reader ENTERS the screen, and carried
///      forward to whatever the screen eventually does.
///
///   2. **A screen that never rendered reported NOTHING.** The bridge only fires
///      from a real first render, so a Discover / Sports / My Stuff load that
///      showed nothing at all emitted no row — and those are precisely the worst
///      rows. The 2026-09-02 battery found 3 of 40 cold loads rendering nothing;
///      not one of them could have appeared in this table. Arming starts a
///      deadline, and a screen still blank when it expires reports `no_card`:
///      a MEASURED FAILURE, not an absence.
///
/// 🔴 ONE ARM PRODUCES AT MOST ONE ROW. The deadline, an explicit outcome and
/// the bridge all race for the same screen entry, and a screen entry that
/// produced two rows would inflate the denominator of every rate computed off
/// this table. Once an arm has reported `no_card` its late arrival is SUPPRESSED
/// until the surface is armed again — the uncensored number is not lost, because
/// the three bespoke rails (`discover_feed_first_render` and friends) still
/// carry it uncensored beside this one.
///
/// Deliberately NOT `@MainActor`. The three existing first-render rails are
/// `nonisolated static` and are the call sites that bridge into this packet;
/// forcing a main-actor hop on them to read one flag would change their timing
/// in the act of reading their own timing. An `NSLock` is the smaller cost.
public enum ScreenTimingSession {
    /// Cancels a scheduled deadline. Returned by the scheduler so tests can
    /// substitute a hand-fired timer and no test has to sleep for ten seconds.
    public typealias DeadlineScheduler = @Sendable (
        TimeInterval,
        @escaping @Sendable () -> Void
    ) -> @Sendable () -> Void

    private static let lock = NSLock()
    nonisolated(unsafe) private static var hasMeasuredFirstScreen = false
    nonisolated(unsafe) private static var arms: [String: Arm] = [:]
    nonisolated(unsafe) private static var armSequence: UInt64 = 0
    nonisolated(unsafe) private static var sink: ScreenTimingSink = AnalyticsScreenTimingSink()
    nonisolated(unsafe) private static var clock: @Sendable () -> Date = { Date() }
    nonisolated(unsafe) private static var schedule: DeadlineScheduler = defaultScheduler

    /// A screen appearing this long after launch is not really a launch screen
    /// even if it is the first one armed — the reader was staring at something.
    /// Keeps a slow launch from being relabelled as a warm screen and vice versa.
    /// Applied at ARM time, so a slow FIRST CARD can no longer trip it.
    static let coldWindowSeconds: TimeInterval = 20

    /// A screen that has shown no card by this long after the reader entered it
    /// is a measured failure, and is reported as one.
    ///
    /// Ten seconds, not the recorder's thirty, and the asymmetry is deliberate:
    /// an armed surface ALSO reports its true first-card time through its own
    /// bespoke rail, so nothing is lost by calling the screen_timing row a
    /// failure early. A `.screenTiming()` screen has no second rail, so its
    /// budget stays at thirty and matches the web's, preserving the number.
    static let noCardDeadlineSeconds: TimeInterval = 10

    /// A reader who leaves a still-blank screen after at least this long did not
    /// flick past it — they waited, saw nothing, and left. That is the failure
    /// the table is for, so it is reported. Below it, a tab flick would
    /// manufacture failures for screens nobody gave a chance.
    static let abandonedBlankSeconds: TimeInterval = 3

    private struct Arm {
        let id: UInt64
        let entry: String
        let armedAt: Date
        var settled = false
        var blanked = false
        var cancelDeadline: (@Sendable () -> Void)?
    }

    private static let defaultScheduler: DeadlineScheduler = { seconds, work in
        let task = Task {
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            guard !Task.isCancelled else { return }
            work()
        }
        return { task.cancel() }
    }

    /// Claim this process's cold/warm label. The FIRST claim after launch is
    /// cold; every later one is warm.
    ///
    /// 🔴 CALL THIS WHEN THE READER ENTERS THE SCREEN, never when the screen
    /// finishes. Both callers do: `armScreen` below, and the `.screenTiming()`
    /// modifier's `onAppear`.
    public static func nextEntry(launchElapsed: TimeInterval = AppLaunchClock.elapsed) -> String {
        lock.lock()
        defer { lock.unlock() }
        let wasFirst = !hasMeasuredFirstScreen
        hasMeasuredFirstScreen = true
        return (wasFirst && launchElapsed <= coldWindowSeconds) ? "cold" : "warm"
    }

    /// The reader just entered `surface` and it is showing no cards yet. Claims
    /// the entry label now and starts the no-card deadline.
    ///
    /// 🔴 ONLY CALL THIS WHEN THE SCREEN IS ACTUALLY BLANK. Arming a tab that is
    /// already displaying its cards would arm a deadline nothing can settle — a
    /// tab switch back to a fully rendered Discover stamps no new render
    /// generation, so the bridge never fires, so ten seconds later the rail would
    /// report a screen full of cards as `no_card`. Every call site guards on its
    /// own `items.isEmpty`.
    @discardableResult
    public static func armScreen(
        surface: String,
        launchElapsed: TimeInterval = AppLaunchClock.elapsed
    ) -> String {
        let entry = nextEntry(launchElapsed: launchElapsed)
        lock.lock()
        armSequence &+= 1
        let id = armSequence
        arms[surface]?.cancelDeadline?()
        arms[surface] = Arm(id: id, entry: entry, armedAt: clock())
        let scheduleRef = schedule
        lock.unlock()

        let cancel = scheduleRef(noCardDeadlineSeconds) { expire(surface: surface, id: id) }
        lock.lock()
        // The deadline can already have fired (a test scheduler fires inline).
        // Only the arm that scheduled it may own its cancel handle.
        if arms[surface]?.id == id {
            arms[surface]?.cancelDeadline = cancel
        } else {
            cancel()
        }
        lock.unlock()
        return entry
    }

    /// The screen produced its first card. Emits one row carrying the label
    /// claimed at ARM time, and stands the deadline down.
    public static func reportBridged(surface: String, firstCardMs: Int, cardCount: Int) {
        var entry: String?
        var suppressed = false
        lock.lock()
        if var arm = arms[surface] {
            if arm.blanked {
                // This screen entry has already been reported as a failure. A
                // second row for the same entry would double-count the load.
                suppressed = true
            } else if arm.settled {
                // A refresh of a screen whose arrival was already reported. A
                // real, separate measurement — and by definition not a launch.
                entry = "warm"
            } else {
                arm.settled = true
                arm.cancelDeadline?()
                arm.cancelDeadline = nil
                arms[surface] = arm
                entry = arm.entry
            }
        }
        let sinkRef = sink
        lock.unlock()

        if suppressed { return }
        // No arm: a screen that reports a first card without having announced its
        // entry. Falls back to the process-level rule, which is what every screen
        // did before arming existed — never silence.
        let resolved = entry ?? nextEntry()
        sinkRef.send(ScreenTimingPacket.bridged(
            surface: surface,
            firstCardMs: firstCardMs,
            cardCount: cardCount,
            entry: resolved
        ))
    }

    /// The screen's load resolved with no card AND the screen knows why —
    /// `empty` (nothing to show) or `error` (the load failed). Distinct from
    /// `no_card`, which is the deadline expiring on a screen that never said.
    ///
    /// A no-op when the surface is not armed or is already settled: the outcome
    /// belongs to a screen entry, and an entry that has already reported has
    /// nothing left to say.
    public static func reportOutcome(surface: String, outcome: String) {
        var entry: String?
        lock.lock()
        if var arm = arms[surface], !arm.settled {
            arm.settled = true
            arm.cancelDeadline?()
            arm.cancelDeadline = nil
            arms[surface] = arm
            entry = arm.entry
        }
        let sinkRef = sink
        lock.unlock()
        guard let resolved = entry else { return }
        sinkRef.send(ScreenTimingPacket.withoutCard(
            surface: surface,
            entry: resolved,
            outcome: outcome
        ))
    }

    /// The reader left `surface`. Stands the deadline down, and reports the
    /// still-blank case as a failure if they actually waited (see
    /// `abandonedBlankSeconds`).
    public static func disarmScreen(surface: String) {
        lock.lock()
        guard let arm = arms.removeValue(forKey: surface) else { lock.unlock(); return }
        arm.cancelDeadline?()
        let dwell = clock().timeIntervalSince(arm.armedAt)
        let report = !arm.settled && dwell >= abandonedBlankSeconds
        let entry = arm.entry
        let sinkRef = sink
        lock.unlock()
        guard report else { return }
        sinkRef.send(ScreenTimingPacket.withoutCard(surface: surface, entry: entry, outcome: "no_card"))
    }

    /// The deadline expired with nothing on screen.
    private static func expire(surface: String, id: UInt64) {
        lock.lock()
        guard var arm = arms[surface], arm.id == id, !arm.settled else {
            lock.unlock()
            return
        }
        arm.settled = true
        arm.blanked = true
        arm.cancelDeadline = nil
        arms[surface] = arm
        let entry = arm.entry
        let sinkRef = sink
        lock.unlock()
        sinkRef.send(ScreenTimingPacket.withoutCard(surface: surface, entry: entry, outcome: "no_card"))
    }

    // MARK: - Test harness

    /// Tests only — the flag and the arm table are process-global by design.
    static func resetForTesting() {
        lock.lock()
        hasMeasuredFirstScreen = false
        for arm in arms.values { arm.cancelDeadline?() }
        arms = [:]
        sink = AnalyticsScreenTimingSink()
        clock = { Date() }
        schedule = defaultScheduler
        lock.unlock()
    }

    /// Tests only. Substitutes the sink, the clock and the deadline timer so an
    /// arm's whole lifecycle can be driven without wall time or Firebase.
    /// Returns nothing; call `resetForTesting()` afterwards.
    static func installTestHarness(
        sink testSink: ScreenTimingSink,
        now: @escaping @Sendable () -> Date,
        schedule testSchedule: @escaping DeadlineScheduler
    ) {
        lock.lock()
        hasMeasuredFirstScreen = false
        for arm in arms.values { arm.cancelDeadline?() }
        arms = [:]
        sink = testSink
        clock = now
        schedule = testSchedule
        lock.unlock()
    }
}

// MARK: - SwiftUI attachment

/// The per-screen wiring, in two words. `.screenTiming("discover")` on the
/// screen, `.firstRealCard()` on the first real row it renders.
///
/// Deliberately NOT an `ObservableObject`, for two independent reasons. Nothing
/// ever observes it — it is a handle passed down the environment and read
/// imperatively, so a publisher would be dead weight that invalidates views for
/// a measurement. And this target builds with
/// `SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY = YES`, under which
/// `ObservableObject` is NOT visible through SwiftUI's re-export of Combine —
/// conforming to it here fails to build unless `import Combine` is added, which
/// would be importing a framework to satisfy a protocol nothing needs.
@MainActor
public final class ScreenTimingBox {
    public private(set) var recorder: ScreenTimingRecorder?
    public init() {}
    func start(surface: String) {
        recorder?.cancel()
        recorder = ScreenTimingRecorder(surface: surface, entry: ScreenTimingSession.nextEntry())
    }
    func stop() {
        recorder?.cancel()
        recorder = nil
    }
}

/// 🔴 An OPTIONAL environment value, deliberately, not `@EnvironmentObject`.
///
/// `@EnvironmentObject` traps at runtime when the object is absent. That would
/// mean `.firstRealCard()` attached anywhere outside a `.screenTiming()` subtree
/// — a card extracted into a reusable component, a preview, a screen somebody
/// wires half of — crashes the app. Instrumentation is never allowed to be the
/// thing that takes the product down; an unattached marker must be a silently
/// missing measurement, which the `no_card` outcome then makes visible anyway.
private struct ScreenTimingBoxKey: EnvironmentKey {
    static let defaultValue: ScreenTimingBox? = nil
}

private extension EnvironmentValues {
    var screenTimingBox: ScreenTimingBox? {
        get { self[ScreenTimingBoxKey.self] }
        set { self[ScreenTimingBoxKey.self] = newValue }
    }
}

private struct ScreenTimingModifier: ViewModifier {
    let surface: String
    // `@State`, not `@StateObject`: the box is not observable (see its note), and
    // `@State` gives the same "created once, survives re-renders" lifetime.
    @State private var box = ScreenTimingBox()

    func body(content: Content) -> some View {
        content
            .environment(\.screenTimingBox, box)
            .onAppear { box.start(surface: surface) }
            .onDisappear { box.stop() }
    }
}

private struct FirstRealCardModifier: ViewModifier {
    @Environment(\.screenTimingBox) private var box: ScreenTimingBox?
    func body(content: Content) -> some View {
        content.onAppear { box?.recorder?.markFirstCard() }
    }
}

/// Declare that the screen is currently showing placeholders. Attach to the
/// loading state so a skeleton can never be counted as the first real card.
private struct ScreenTimingLoadingModifier: ViewModifier {
    let loading: Bool
    @Environment(\.screenTimingBox) private var box: ScreenTimingBox?
    func body(content: Content) -> some View {
        content
            .onAppear { box?.recorder?.markLoading(loading) }
            .onChange(of: loading) { _, newValue in box?.recorder?.markLoading(newValue) }
    }
}

public extension View {
    /// Measure this screen. `surface` is a bounded slug, never an id.
    func screenTiming(_ surface: String) -> some View {
        modifier(ScreenTimingModifier(surface: surface))
    }

    /// Mark this view as the first REAL card. Must not be attached to a
    /// placeholder — see `ScreenTimingRecorder`'s note on skeletons. Safe to
    /// attach outside a measured screen: it becomes a no-op, never a crash.
    func firstRealCard() -> some View {
        modifier(FirstRealCardModifier())
    }

    /// Tell the rail this screen is showing placeholders right now. Belt and
    /// braces beside `.firstRealCard()`: a marker that slips onto a skeleton is
    /// then ignored rather than believed.
    func screenTimingLoading(_ loading: Bool) -> some View {
        modifier(ScreenTimingLoadingModifier(loading: loading))
    }
}
