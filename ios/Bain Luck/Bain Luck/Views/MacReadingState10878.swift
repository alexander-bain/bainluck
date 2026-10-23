import SwiftUI
#if os(macOS)
import AppKit
#endif

/// #10878 — where a Mac reader was on each screen, held by the window ABOVE the
/// screen's mount.
///
/// The Mac window mounts one destination at a time (`MacMainWindowView`), so
/// leaving a screen ends its tasks, sockets and timers through the screen's own
/// `onDisappear` — nothing offscreen keeps working. Before this, that same
/// unmount also threw away everything the screen owned: Search's query and
/// results, the detail a reader had open, and how far down they had read. A
/// round trip through My Stuff landed them back on an empty Search field at the
/// top.
///
/// A `MacReadingPlace` keeps exactly those things across the unmount — the
/// screen's view model(s), its navigation path, how many cards it had revealed
/// and its scroll offset — and the screen adopts them when it mounts again. It
/// keeps no subscription or repeating work of its own; the screen still stops
/// its sockets, timers and typeahead on the way out. The one thing it does hold
/// is Discover's first load while that load is still running, so a reader who
/// leaves and comes back mid-load joins it instead of starting a second one
/// (`runInitialLoad`). Models are kept for the whole account session and
/// dropped only when the account changes (`MacReadingState10878`).
///
/// Only the Mac window passes a place. Every other caller gets `nil` and the
/// screens behave exactly as they always have.
@MainActor
final class MacReadingPlace<Models> {
    private(set) var models: Models?
    var path = NavigationPath()
    /// Discover's paging position: how many cards were revealed. `nil` until the
    /// screen has reported one.
    var revealedCount: Int?
    /// Where the screen's main scroll view was.
    var scrollPlace = MacScrollPlace()

    /// The screen's models: the retained ones if this place holds some, otherwise
    /// `make()`'s, which the place then keeps. Called from inside the screen's
    /// `StateObject` autoclosure, so it only runs when SwiftUI actually creates
    /// the screen's state.
    func models(orMake make: () -> Models) -> Models {
        if let models { return models }
        let made = make()
        models = made
        return made
    }

    /// The screen's first load, while it is still running.
    private var initialLoad: Task<Void, Never>?

    /// Runs the screen's first load — or, if the load this place started is
    /// still running, waits for that one instead of starting another beside it.
    ///
    /// The load runs in its own unstructured task, as
    /// `DiscoverView.loadForInitialAppearance` already does (#10399 / #10094):
    /// a seeded deck must still revalidate after SwiftUI tears the appearance
    /// task down, so a reader who leaves mid-load does not cancel it.
    func runInitialLoad(_ load: @escaping @MainActor () async -> Void) async {
        if let running = initialLoad {
            await running.value
            return
        }
        let task = Task { @MainActor in await load() }
        initialLoad = task
        await task.value
        initialLoad = nil
    }
}

extension MacReadingPlace: MacScrollOffsetHolding {}

/// What the Mac's scroll keeper reads and writes.
@MainActor
protocol MacScrollOffsetHolding: AnyObject {
    var scrollPlace: MacScrollPlace { get set }
}

/// A scroll position. `offset` is points from the top. For a List the keeper
/// also notes the first visible row and how far into it the reader was: a
/// List's row heights are estimated until laid out, so the same pixel offset
/// lands half a row away after a remount (measured, macOS 26), while the row
/// does not move.
struct MacScrollPlace: Equatable {
    var offset: CGFloat = 0
    var row: Int?
    var offsetInRow: CGFloat = 0

    /// The offset to return to: the remembered row's top as laid out NOW plus
    /// the distance into it, when there is a row; otherwise the plain offset.
    func target(rowTop: CGFloat?) -> CGFloat {
        if row != nil, let rowTop { return max(0, rowTop + offsetInRow) }
        return offset
    }
}

/// #10878 — the three screens whose place the Mac window keeps, for ONE signed-in
/// identity. Owned by `MacMainWindowView` as plain state, so each window keeps
/// its own and nothing is shared between windows.
@MainActor
final class MacReadingState10878 {

    /// My Stuff owns two models; they are kept and released together.
    struct MyStuffModels {
        let feed: MyStuffViewModel
        let pins: SavedPinContentViewModel
        init() {
            feed = MyStuffViewModel()
            pins = SavedPinContentViewModel()
        }
    }

    final class Places {
        /// Changes whenever the identity does. The window keys the mounted screen
        /// on it, so an account change also rebuilds the screen on view.
        let generation: Int
        let discover = MacReadingPlace<DiscoverViewModel>()
        let search = MacReadingPlace<SearchViewModel>()
        let myStuff = MacReadingPlace<MyStuffModels>()
        init(generation: Int) { self.generation = generation }
    }

    private var identity: String?
    private var current: Places?
    private var generation = 0

    /// The places for `identity` (`AuthManager.activeFeedUserId`; `nil` is a
    /// guest). A different identity from the last call discards every kept
    /// place — the previous account's results, open details and models — and
    /// starts empty, so one person's reading never shows under another's
    /// account, even for screens that were offscreen when the account changed.
    /// Plain storage, not observed: reading this from `body` publishes nothing.
    func places(for identity: String?) -> Places {
        if let current, identity == self.identity { return current }
        self.identity = identity
        generation &+= 1
        let fresh = Places(generation: generation)
        current = fresh
        return fresh
    }
}

/// #10878 — the scroll keeper's two decisions, as plain arithmetic so they are
/// testable away from AppKit.
enum MacReadingOffset10878 {

    /// Record a scroll position only when the content is really there. A scroll
    /// view being torn down (or not yet laid out) reports offset 0 over an empty
    /// document; recording that would overwrite the reader's place on the way
    /// out. Nothing is recorded while a restore is still pending either: until
    /// then every bounds change is layout or the restore itself. A reader who
    /// scrolls ends the pending restore first (`MacScrollRestore10878`), so their
    /// scroll is recorded.
    static func shouldRecord(documentHeight: CGFloat, visibleHeight: CGFloat, restorePending: Bool) -> Bool {
        !restorePending && documentHeight > visibleHeight
    }

    enum Restore: Equatable {
        case nothing
        case wait
        case scroll(to: CGFloat)
    }

    /// Lazy content grows over a few layout passes after a mount, so wait until
    /// the document can hold the saved offset; after `maxAttempts` passes, go as
    /// far as the content allows rather than leave the reader at the top.
    static let maxAttempts = 20

    static func restore(saved: CGFloat, documentHeight: CGFloat, visibleHeight: CGFloat, attempts: Int) -> Restore {
        guard saved > 0 else { return .nothing }
        let furthest = max(0, documentHeight - visibleHeight)
        if furthest >= saved { return .scroll(to: saved) }
        if attempts < maxAttempts { return .wait }
        return furthest > 0 ? .scroll(to: furthest) : .nothing
    }

}

/// #10878 — one pending return to a saved place, as plain state so its rules are
/// testable away from AppKit.
///
/// A restore waits for lazy content over several layout passes, retrying on a
/// timer. Two things end it early: the reader scrolling (their new place wins —
/// a later retry must not pull them back to the old one) and the screen leaving
/// the window. A retry carries the `ticket` of the restore it was queued for,
/// and does nothing once that restore has ended or a newer one has begun, so a
/// retry queued before the reader scrolled, or before a leave and return, can
/// never move the reader.
struct MacScrollRestore10878 {
    private(set) var pending: MacScrollPlace?
    private(set) var ticket = 0
    private var attempts = 0

    var isPending: Bool { pending != nil }

    /// Starts returning to `place`, replacing any restore already waiting.
    @discardableResult
    mutating func begin(_ place: MacScrollPlace) -> Int {
        ticket &+= 1
        pending = place
        attempts = 0
        return ticket
    }

    /// The reader scrolled, the screen left the window, or the restore has
    /// moved the reader. Returns whether a restore was still waiting.
    @discardableResult
    mutating func end() -> Bool {
        let wasPending = pending != nil
        pending = nil
        attempts = 0
        return wasPending
    }

    /// One pass of the restore `ticket` names, against the layout as it is now
    /// (`rowTop` is where `pending.row` is laid out, when it is). `nil` when that
    /// restore has since ended: the caller does nothing. On `.scroll` the restore
    /// stays pending while the caller moves, so the bounds change the move causes
    /// is not recorded as the reader's; the caller then calls `end()`.
    mutating func step(ticket: Int, rowTop: CGFloat?, documentHeight: CGFloat, visibleHeight: CGFloat) -> MacReadingOffset10878.Restore? {
        guard ticket == self.ticket, let pending else { return nil }
        let decision = MacReadingOffset10878.restore(
            saved: pending.target(rowTop: rowTop),
            documentHeight: documentHeight,
            visibleHeight: visibleHeight,
            attempts: attempts
        )
        switch decision {
        case .wait: attempts += 1
        case .nothing: self.pending = nil
        case .scroll: break
        }
        return decision
    }
}

extension View {
    /// #10878 — keeps this scroll view's offset in `place` on the Mac and puts
    /// it back when the screen mounts again. Does nothing elsewhere, or with no
    /// place.
    @ViewBuilder
    func macReadingOffset(_ place: (any MacScrollOffsetHolding)?) -> some View {
        #if os(macOS)
        if let place {
            background(MacScrollOffsetKeeper(place: place))
        } else {
            self
        }
        #else
        self
        #endif
    }
}

#if os(macOS)
/// Sits behind a SwiftUI `ScrollView` or `List` and works on the `NSScrollView`
/// AppKit draws it with. SwiftUI's own `ScrollPosition` cannot do this here: on
/// macOS it does not move a `List` at all (measured, macOS 26), and Search's
/// results and My Stuff's feed are Lists.
private struct MacScrollOffsetKeeper: NSViewRepresentable {
    let place: any MacScrollOffsetHolding

    func makeNSView(context: Context) -> KeeperView {
        let view = KeeperView()
        view.place = place
        return view
    }

    func updateNSView(_ view: KeeperView, context: Context) {
        view.place = place
    }

    final class KeeperView: NSView {
        weak var place: (any MacScrollOffsetHolding)?
        private weak var scrollView: NSScrollView?
        nonisolated(unsafe) private var observers: [NSObjectProtocol] = []
        nonisolated(unsafe) private var inputMonitor: Any?
        private var restoring = MacScrollRestore10878()
        /// Changes every time the keeper enters or leaves a window, so a find
        /// queued during an earlier visit does nothing.
        private var visit = 0
        private var findAttempts = 0

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            visit &+= 1
            detach()
            guard window != nil else { return }
            if let saved = place?.scrollPlace { restoring.begin(saved) }
            findAttempts = 0
            let visit = self.visit
            DispatchQueue.main.async { [weak self] in self?.attach(visit: visit) }
        }

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        /// The scroll view this keeper sits behind: the smallest visible one in
        /// the window whose frame contains the keeper's. A pushed detail's scroll
        /// view cannot be picked, because the screen's own root — and this
        /// keeper with it — is out of the window while a detail is showing.
        private func attach(visit: Int) {
            guard visit == self.visit, let window, let root = window.contentView else { return }
            let mine = convert(bounds, to: nil)
            guard mine.width > 0, mine.height > 0 else { return retryAttach(visit: visit) }
            let found = Self.scrollViews(in: root)
                .filter { !$0.isHiddenOrHasHiddenAncestor && $0.convert($0.bounds, to: nil).insetBy(dx: -1, dy: -1).contains(mine) }
                .min { Self.area($0) < Self.area($1) }
            guard let found else { return retryAttach(visit: visit) }
            stopObserving()
            scrollView = found
            found.contentView.postsBoundsChangedNotifications = true
            let center = NotificationCenter.default
            observers = [
                center.addObserver(forName: NSView.boundsDidChangeNotification, object: found.contentView, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { self?.record() }
                },
                // A trackpad gesture or a scroller drag. AppKit posts this
                // before the first bounds change of the reader's scroll.
                center.addObserver(forName: NSScrollView.willStartLiveScrollNotification, object: found, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { self?.readerScrolled() }
                },
            ]
            if restoring.isPending { watchForReaderInput() }
            restore(ticket: restoring.ticket)
        }

        private func retryAttach(visit: Int) {
            findAttempts += 1
            guard findAttempts <= MacReadingOffset10878.maxAttempts else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.attach(visit: visit) }
        }

        private func record() {
            guard let scrollView else { return }
            let clip = scrollView.contentView
            guard MacReadingOffset10878.shouldRecord(
                documentHeight: scrollView.documentView?.frame.height ?? 0,
                visibleHeight: clip.bounds.height,
                restorePending: restoring.isPending
            ) else { return }
            let y = clip.bounds.origin.y
            var recorded = MacScrollPlace(offset: y)
            if let table = scrollView.documentView as? NSTableView {
                let row = table.row(at: NSPoint(x: table.bounds.midX, y: max(0, y)))
                if row >= 0 {
                    recorded.row = row
                    recorded.offsetInRow = y - table.rect(ofRow: row).minY
                }
            }
            place?.scrollPlace = recorded
        }

        private func restore(ticket: Int) {
            guard let scrollView else { return }
            let clip = scrollView.contentView
            var rowTop: CGFloat?
            if let row = restoring.pending?.row, let table = scrollView.documentView as? NSTableView, row < table.numberOfRows {
                rowTop = table.rect(ofRow: row).minY
            }
            switch restoring.step(
                ticket: ticket,
                rowTop: rowTop,
                documentHeight: scrollView.documentView?.frame.height ?? 0,
                visibleHeight: clip.bounds.height
            ) {
            case nil:
                return
            case .nothing:
                stopWatchingForReaderInput()
            case .wait:
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in self?.restore(ticket: ticket) }
            case .scroll(let y):
                clip.scroll(to: NSPoint(x: clip.bounds.origin.x, y: y))
                scrollView.reflectScrolledClipView(clip)
                restoring.end()
                stopWatchingForReaderInput()
            }
        }

        /// The reader moved the scroll view while a restore was waiting: their
        /// new place wins. The waiting restore is dropped — any retry already
        /// queued finds its ticket gone — and recording resumes, so this scroll
        /// and everything after it is kept.
        private func readerScrolled() {
            guard restoring.end() else { return }
            stopWatchingForReaderInput()
            record()
        }

        /// Scrolling that posts no live-scroll notification — a mouse wheel, or
        /// the scrolling keys with focus inside this scroll view — is seen here,
        /// before AppKit acts on it. Installed only while a restore waits.
        private func watchForReaderInput() {
            guard inputMonitor == nil else { return }
            inputMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .keyDown]) { [weak self] event in
                let input = MacReaderInput(event)
                MainActor.assumeIsolated { self?.noteInput(input) }
                return event
            }
        }

        private func noteInput(_ input: MacReaderInput) {
            guard restoring.isPending, let scrollView, let window = scrollView.window,
                  input.windowNumber == window.windowNumber else { return }
            if input.isWheel {
                guard scrollView.bounds.contains(scrollView.convert(input.locationInWindow, from: nil)) else { return }
            } else {
                guard input.isScrollingKey,
                      let focused = window.firstResponder as? NSView,
                      !(focused is NSText),
                      focused.isDescendant(of: scrollView) else { return }
            }
            readerScrolled()
        }

        private func stopWatchingForReaderInput() {
            if let inputMonitor { NSEvent.removeMonitor(inputMonitor) }
            inputMonitor = nil
        }

        /// Leaving the window ends everything this visit started: observers,
        /// the input watch, and any restore still waiting.
        private func detach() {
            stopObserving()
            restoring.end()
            scrollView = nil
        }

        private func stopObserving() {
            observers.forEach { NotificationCenter.default.removeObserver($0) }
            observers = []
            stopWatchingForReaderInput()
        }

        private static func scrollViews(in view: NSView) -> [NSScrollView] {
            var found: [NSScrollView] = []
            if let scroll = view as? NSScrollView { found.append(scroll) }
            for sub in view.subviews { found += scrollViews(in: sub) }
            return found
        }

        private static func area(_ view: NSView) -> CGFloat {
            let frame = view.convert(view.bounds, to: nil)
            return frame.width * frame.height
        }

        deinit {
            observers.forEach { NotificationCenter.default.removeObserver($0) }
            if let inputMonitor { NSEvent.removeMonitor(inputMonitor) }
        }
    }
}

/// The parts of an input event the keeper reads, copied out of the monitor so
/// nothing non-sendable crosses into main-actor code.
nonisolated private struct MacReaderInput: Sendable {
    let windowNumber: Int
    let locationInWindow: NSPoint
    let isWheel: Bool
    let isScrollingKey: Bool

    init(_ event: NSEvent) {
        windowNumber = event.windowNumber
        locationInWindow = event.locationInWindow
        isWheel = event.type == .scrollWheel
        // Key properties throw on any other event type, so read them only for a key.
        if event.type == .keyDown, let key = event.specialKey {
            isScrollingKey = [.pageUp, .pageDown, .home, .end, .upArrow, .downArrow].contains(key)
        } else {
            isScrollingKey = false
        }
    }
}
#endif
