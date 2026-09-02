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
    static func bridged(
        surface: String,
        firstCardMs: Int,
        cardCount: Int,
        entry: String = ScreenTimingSession.nextEntry()
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

// MARK: - Cold / warm

/// Decides `cold` vs `warm` for the whole process. The FIRST screen measured
/// after launch is cold; everything after it is a warm in-app transition. The
/// two have different targets (<3 s cold, <1 s warm), so blending them would
/// hide the only distinction the target is written in.
/// Deliberately NOT `@MainActor`. The three existing first-render rails
/// (`trackDiscoverFirstRender` and friends) are `nonisolated static` and are the
/// call sites that bridge into this packet; forcing a main-actor hop on them to
/// read one boolean would change their timing to read their own timing. An
/// `NSLock` around one flag is the smaller cost.
public enum ScreenTimingSession {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var hasMeasuredFirstScreen = false
    /// A screen appearing this long after launch is not really a launch screen
    /// even if it is the first one measured — the reader was staring at
    /// something. Keeps a slow launch from being relabelled as a warm screen and
    /// vice versa.
    static let coldWindowSeconds: TimeInterval = 20

    public static func nextEntry(launchElapsed: TimeInterval = AppLaunchClock.elapsed) -> String {
        lock.lock()
        defer { lock.unlock() }
        let wasFirst = !hasMeasuredFirstScreen
        hasMeasuredFirstScreen = true
        return (wasFirst && launchElapsed <= coldWindowSeconds) ? "cold" : "warm"
    }

    /// Tests only — the flag is process-global by design.
    static func resetForTesting() {
        lock.lock()
        hasMeasuredFirstScreen = false
        lock.unlock()
    }
}

// MARK: - SwiftUI attachment

/// The per-screen wiring, in two words. `.screenTiming("discover")` on the
/// screen, `.firstRealCard()` on the first real row it renders.
@MainActor
public final class ScreenTimingBox: ObservableObject {
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
    @StateObject private var box = ScreenTimingBox()

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
