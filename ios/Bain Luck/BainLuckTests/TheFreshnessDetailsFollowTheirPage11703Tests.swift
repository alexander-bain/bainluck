import Combine
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #11703 — **the freshness details belong to the page that opened them.**
///
/// Build 89 on Alex's iPhone (#10090 B3 hold, Chelsea @ Liverpool, 10/28): the
/// app came back from the background and a link opened the game. An "Update
/// interrupted — Last probability update received 34 minutes ago" popover was
/// already up over the new page, before it had loaded, and stayed for the whole
/// three minutes while the headline and chart underneath updated live and the
/// page's own status button read healthy. The receipt time never moved; the age
/// kept counting.
///
/// Mechanism: a link PUSHES the game onto the stack (`FeedView` appends the
/// route). The page underneath stops its refresh when it is covered, but the
/// popover it presented is UIKit's, above the whole stack, so it stays up over
/// the new page and keeps reading the covered page's frozen model — which, with
/// nothing arriving, ages into "interrupted". A unit render cannot see this:
/// the presentation is the window's, so the guard hosts the real page in a
/// real window, opens the details the way VoiceOver does, and pushes.
@MainActor
final class TheFreshnessDetailsFollowTheirPage11703Tests: XCTestCase {
    private static let first = 11_703, second = 11_704

    /// SwiftUI builds its accessibility tree only for an assistive client; a
    /// test process has none, so the page's controls are invisible to it
    /// (measured: zero labels). Automation mode is what an XCUITest runner
    /// turns on; the same switch here lets the test find and activate the
    /// page's real control, the way VoiceOver would.
    override class func setUp() {
        super.setUp()
        setAutomation(true)
    }

    /// Off again, so no later suite in the process renders under it.
    override class func tearDown() {
        setAutomation(false)
        super.tearDown()
    }

    private static func setAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        func fetchEvent(id: Int) async throws -> EventDetail {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            var event = try decoder.decode(EventDetail.self, from: Data(#"{"id":\#(id),"home_team":"Dallas Cowboys","away_team":"Baltimore Ravens","sport":"americanfootball_nfl","status":"live","home_score":24,"away_score":27,"current_odds":{"home_probability":0.45,"away_probability":0.55,"home_rendered_percent":45,"away_rendered_percent":55},"hero_probability":0.45,"hero_probability_source":"blend","blend_fold_revision":{"\#(id)":20},"win_probability_sources":{"kalshi":{"value":0.45,"updated_at":"2026-09-27T23:44:48Z"}}}"#.utf8))
            event.heroProbabilityObservedAt = ISO8601DateFormatter().string(from: Date())
            return event
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var callbacks: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            callbacks[event, default: []].append(handler)
        }
        func close() {}
        func open() { for handler in callbacks["open"] ?? [] { handler("") } }
    }

    /// The app's route stack in miniature: a link appends, exactly as
    /// `FeedView`'s `pendingRoute` handler does.
    private final class Router: ObservableObject {
        @Published var path: [Int] = []
    }

    private struct Stack: View {
        @ObservedObject var router: Router
        let pages: [Int: EventDetailViewModel]
        var body: some View {
            NavigationStack(path: $router.path) {
                EventDetailView(eventId: TheFreshnessDetailsFollowTheirPage11703Tests.first,
                                viewModel: pages[TheFreshnessDetailsFollowTheirPage11703Tests.first])
                    .navigationDestination(for: Int.self) { id in
                        EventDetailView(eventId: id, viewModel: pages[id])
                    }
            }
        }
    }

    private func liveModel(_ id: Int) async -> EventDetailViewModel {
        let handle = PageHandle()
        let vm = EventDetailViewModel(eventId: id, client: PageClient(), makeStreamHandle: { _ in handle })
        await vm.load(); handle.open()
        return vm
    }

    /// A popover needs a window on a foreground-active scene (the
    /// `EventPublicationCaller4974Tests.MountedPage` pattern).
    private func mount<V: View>(_ view: V) async throws -> (UIViewController, UIWindow, UIWindow?) {
        let deadline = Date().addingTimeInterval(10)
        func activeScene() -> UIWindowScene? {
            UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
                .first { $0.activationState == .foregroundActive }
        }
        while activeScene() == nil && Date() < deadline { try await Task.sleep(nanoseconds: 50_000_000) }
        let scene = try XCTUnwrap(activeScene(), "a popover needs a foreground-active window scene")
        let previous = scene.windows.first { $0.isKeyWindow }
        let host = hostForMeasurement(view.environmentObject(PinManager())
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(windowScene: scene)
        window.frame = host.view.frame
        window.rootViewController = host
        window.makeKeyAndVisible()
        return (host, window, previous)
    }

    /// Lays out and yields (never a nested run loop: the page's tasks are
    /// main-actor jobs) until `condition` holds or `timeout` passes.
    @discardableResult
    private func settle(_ host: UIViewController, timeout: TimeInterval,
                        until condition: () -> Bool = { false }) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            if condition() { return true }
            try? await Task.sleep(nanoseconds: 20_000_000)
        } while Date() < deadline
        return condition()
    }

    /// The view of the page on top of the stack: a covered page stays in the
    /// hierarchy, so its control must not answer for the page on screen.
    private func topPage(_ controller: UIViewController) -> UIView {
        func stack(_ c: UIViewController) -> UINavigationController? {
            if let nav = c as? UINavigationController { return nav }
            return c.children.lazy.compactMap(stack).first
        }
        return stack(controller)?.topViewController?.view ?? controller.view
    }

    /// H PROBE (#11703, DO NOT MERGE): what holds every dismissal after the
    /// push until ~+5.2 s? Against CACurrentMediaTime (the clock of G's DIAG
    /// lines) it records the host's and the navigation controller's
    /// transitionCoordinator, the popover's isBeingPresented/isBeingDismissed
    /// and its own coordinator, and the completion time of every coordinator
    /// it sees. A run-loop observer prints on every change; a timer prints
    /// every 0.25 s until the popover is gone (+1 s), capped at 10 s.
    @MainActor private final class HProbe {
        let host: UIViewController
        weak var popover: UIViewController?
        let popoverId: String
        var timer: Timer?
        var observer: CFRunLoopObserver?
        var last = ""
        var hooked: [ObjectIdentifier] = []
        var goneAt: CFTimeInterval?
        var startedAt: CFTimeInterval = 0

        init(host: UIViewController) {
            self.host = host
            popover = host.presentedViewController
            popoverId = host.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil"
        }

        static func nav(_ c: UIViewController) -> UINavigationController? {
            if let nav = c as? UINavigationController { return nav }
            return c.children.lazy.compactMap { Self.nav($0) }.first
        }

        static func id(_ o: AnyObject?) -> String { o.map { String(describing: ObjectIdentifier($0)) } ?? "nil" }

        static func coord(_ c: UIViewControllerTransitionCoordinator?) -> String {
            guard let c else { return "nil" }
            return "set(\(id(c as AnyObject)) animated=\(c.isAnimated) interactive=\(c.isInteractive) "
                + "duration=\(c.transitionDuration) style=\(c.presentationStyle.rawValue) "
                + "from=\(id(c.viewController(forKey: .from))) to=\(id(c.viewController(forKey: .to))))"
        }

        func state() -> String {
            let nav = Self.nav(host)
            return "hostCoord=\(Self.coord(host.transitionCoordinator)) navCoord=\(Self.coord(nav?.transitionCoordinator)) "
                + "nav=\(Self.id(nav)) navCount=\(nav?.viewControllers.count ?? -1) top=\(Self.id(nav?.topViewController)) "
                + "presented=\(Self.id(host.presentedViewController)) pop=\(popoverId) popAlive=\(popover != nil) "
                + "popPresenter=\(popover?.presentingViewController != nil) popInWindow=\(popover?.viewIfLoaded?.window != nil) "
                + "popBeingPresented=\(popover?.isBeingPresented ?? false) popBeingDismissed=\(popover?.isBeingDismissed ?? false) "
                + "popCoord=\(Self.coord(popover?.transitionCoordinator))"
        }

        /// Hooks the completion of each coordinator once.
        func hook(_ c: UIViewControllerTransitionCoordinator?, _ which: String) {
            guard let c else { return }
            let key = ObjectIdentifier(c as AnyObject)
            guard !hooked.contains(key) else { return }
            hooked.append(key)
            let label = Self.id(c as AnyObject)
            let queued = c.animate(alongsideTransition: nil) { context in
                print("H11703 coordinatorDone t=\(CACurrentMediaTime()) which=\(which) coord=\(label) cancelled=\(context.isCancelled)")
            }
            print("H11703 coordinatorHooked t=\(CACurrentMediaTime()) which=\(which) coord=\(label) queued=\(queued)")
        }

        func sample(_ why: String, onlyOnChange: Bool) {
            let now = CACurrentMediaTime()
            hook(host.transitionCoordinator, "host")
            hook(Self.nav(host)?.transitionCoordinator, "nav")
            hook(popover?.transitionCoordinator, "popover")
            let s = state()
            if onlyOnChange && s == last { return }
            last = s
            print("H11703 \(why) t=\(now) dt=\(startedAt == 0 ? 0 : now - startedAt) \(s)")
            if goneAt == nil, popover?.presentingViewController == nil {
                goneAt = now
                print("H11703 popoverGone t=\(now) dt=\(now - startedAt)")
            }
            if let goneAt, now - goneAt > 1 { stop("gone+1s") } else if startedAt > 0, now - startedAt > 10 { stop("cap10s") }
        }

        func mark(_ why: String) {
            if why == "push" { startedAt = CACurrentMediaTime() }
            sample(why, onlyOnChange: false)
        }

        func start() {
            let observer = CFRunLoopObserverCreateWithHandler(
                kCFAllocatorDefault,
                CFRunLoopActivity.beforeSources.rawValue | CFRunLoopActivity.beforeWaiting.rawValue
                    | CFRunLoopActivity.afterWaiting.rawValue,
                true, 0
            ) { [weak self] _, _ in
                MainActor.assumeIsolated { self?.sample("change", onlyOnChange: true) }
            }
            CFRunLoopAddObserver(CFRunLoopGetMain(), observer, .commonModes)
            self.observer = observer
            let timer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.sample("tick", onlyOnChange: false) }
            }
            RunLoop.main.add(timer, forMode: .common)
            self.timer = timer
        }

        func stop(_ why: String) {
            guard timer != nil || observer != nil else { return }
            timer?.invalidate(); timer = nil
            if let observer { CFRunLoopRemoveObserver(CFRunLoopGetMain(), observer, .commonModes) }
            observer = nil
            print("H11703 stop t=\(CACurrentMediaTime()) why=\(why)")
        }
    }

    /// The page's details control, found the way VoiceOver finds it.
    private func detailsControl(in root: NSObject) -> NSObject? {
        if let label = root.accessibilityLabel,
           label.hasPrefix("Probability confidence and update details") { return root }
        var children: [NSObject] = []
        if let elements = root.accessibilityElements as? [NSObject] { children += elements }
        let count = root.accessibilityElementCount()
        if count != NSNotFound, count > 0 {
            children += (0..<count).compactMap { root.accessibilityElement(at: $0) as? NSObject }
        }
        if let view = root as? UIView { children += view.subviews }
        for child in children {
            if let found = detailsControl(in: child) { return found }
        }
        return nil
    }

    private func onScreenText(_ window: UIWindow, _ name: String) throws -> String {
        let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
            window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("freshness-11703-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
        print("FRESHNESS11703 \(name) evidence=\(url.path) text=\(text)")
        return text
    }

    /// RED on 1f77f984 (build 89's tree): the details opened on the first game
    /// are still presented after a link pushes the second game.
    func testALinkToAnotherGameClosesTheDetailsTheCoveredPageOpened() async throws {
        let router = Router()
        let pages = [Self.first: await liveModel(Self.first), Self.second: await liveModel(Self.second)]
        defer { pages.values.forEach { $0.stopRefresh() } }
        let (host, window, previous) = try await mount(Stack(router: router, pages: pages))
        defer { host.dismiss(animated: false); window.isHidden = true; previous?.makeKey() }

        var control: NSObject?
        await settle(host, timeout: 5) { control = self.detailsControl(in: self.topPage(host)); return control != nil }
        let opener = try XCTUnwrap(control, "control: the first game's page shows its details control")
        XCTAssertTrue(opener.accessibilityActivate(), "control: the details control takes an activation")
        let opened = await settle(host, timeout: 3) { host.presentedViewController != nil }
        XCTAssertTrue(opened, "control: a reader who opens the details sees them")
        _ = try onScreenText(window, "first-page-details-open")

        let probe = HProbe(host: host)
        probe.mark("prePush")
        probe.start()
        defer { probe.stop("testEnd") }
        router.path.append(Self.second)
        probe.mark("push")
        print("DIAG11703S push t=\(CACurrentMediaTime()) presented=\(host.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
        var seen = host.presentedViewController.map(ObjectIdentifier.init)
        await settle(host, timeout: 1.5) {
            let now = host.presentedViewController.map(ObjectIdentifier.init)
            if now != seen { print("DIAG11703S presentedChanged t=\(CACurrentMediaTime()) to=\(now.map { String(describing: $0) } ?? "nil")"); seen = now }
            return router.path.count == 1 && host.presentedViewController == nil
        }
        print("DIAG11703S settled t=\(CACurrentMediaTime()) presented=\(host.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
        let leftOver = host.presentedViewController
        _ = try onScreenText(window, "after-link-to-second-game")
        XCTAssertNil(leftOver,
            "#11703: the first game's freshness details (\(leftOver.map { String(describing: type(of: $0)) } ?? "-")) "
            + "are still up over the second game's page after the link")

        // The reader's own reveal still works on the page they are now on.
        var secondControl: NSObject?
        await settle(host, timeout: 5) {
            secondControl = self.detailsControl(in: self.topPage(host)); return secondControl != nil
        }
        XCTAssertTrue(try XCTUnwrap(secondControl, "the second game shows its own details control")
            .accessibilityActivate())
        let reopened = await settle(host, timeout: 3) { host.presentedViewController != nil }
        XCTAssertTrue(reopened, "the second game's own details still open when the reader asks")

        // The first page's own close comes seconds after the push on iOS 27
        // (its `onDisappear`); it must not take the second game's details
        // with it.
        let secondDetails = host.presentedViewController
        let started = Date()
        print("DIAG11703S secondDetails=\(secondDetails.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
        await settle(host, timeout: 6) {
            if host.presentedViewController !== secondDetails {
                print("DIAG11703S secondDetailsChanged after=\(Date().timeIntervalSince(started)) now=\(host.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
                return true
            }
            return false
        }
        XCTAssertTrue(secondDetails != nil && host.presentedViewController === secondDetails,
            "#11703: the second game's details closed on their own after the first page's late close")
    }
}
