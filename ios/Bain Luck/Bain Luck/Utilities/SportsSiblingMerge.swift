import Foundation

/// A deadline-bounded, order-independent merge channel for the native **Sports**
/// tab's optional sibling loads (L2-211 Item 1 / C73).
///
/// The Sports tab's two supplemental requests (events-only backfill, grouped
/// futures) run as OWNED, cancellable, unstructured tasks so a superseding load or a
/// disappearing view can cancel them. Each task calls `deliver(_:)` exactly once on
/// completion, and the load consumes results with `next()`. `close()` (fired by a
/// deadline) makes a waiting `next()` return `nil`.
///
/// Why not a structured `withTaskGroup`? A task group awaits ALL of its children on
/// scope exit, so a single sibling that IGNORES cancellation (never returns) would
/// keep the group — and therefore the whole load rail — alive indefinitely. Routing
/// results through this channel lets the load stop waiting at the deadline while the
/// runaway sibling is simply abandoned: its late `deliver(_:)` after `close()` is
/// dropped, and the caller's load-generation guard is the second backstop against a
/// late mutate. `T` is the sibling-result payload (`FeedViewModel.SiblingResult`).
final class SportsSiblingMerge<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var queue: [T] = []
    private var closed = false
    private var pending: CheckedContinuation<T?, Never>?

    /// Explicit, and load-bearing: it is what makes the app archivable. Same
    /// Swift 6.3.3 codegen bug as `MemoizedPresentation` — `EarlyPerfInliner`
    /// crashes inlining into a generic class's *synthesized* deallocating
    /// destructor, so `-O` builds die on `@$s9Bain_Luck18SportsSiblingMergeCfD`
    /// while every Debug build and all of CI stay green. Writing the destructor
    /// out by hand gives the pass a real body. See the note on
    /// `MemoizedPresentation.deinit` for the full account; these are the only two
    /// generic classes in the target and `ReleaseBuildArchivabilityTests` pins
    /// that fact so a third cannot be added without this deinit.
    ///
    /// Releases exactly what the synthesized destructor released, and no more.
    /// In particular it does **not** resume `pending`: dropping an unresumed
    /// `CheckedContinuation` is what deallocating this channel has always done,
    /// and resuming here would change behaviour, not preserve it.
    deinit {
        queue.removeAll()
        pending = nil
    }

    /// Deliver one sibling result. Handed to a waiting `next()` immediately, or
    /// buffered until the next `next()`. Dropped once the channel is closed, so a
    /// cancellation-ignoring sibling that returns after the deadline cannot publish.
    func deliver(_ value: T) {
        let resume: CheckedContinuation<T?, Never>?
        lock.lock()
        if closed {
            lock.unlock()
            return
        }
        if let waiter = pending {
            pending = nil
            lock.unlock()
            waiter.resume(returning: value)
            return
        }
        queue.append(value)
        resume = nil
        lock.unlock()
        _ = resume
    }

    /// Close the channel: a currently-suspended `next()` gets `nil`, and every later
    /// `next()`/`deliver()` is inert. Idempotent. Fired by the load's deadline.
    func close() {
        let waiter: CheckedContinuation<T?, Never>?
        lock.lock()
        if closed {
            lock.unlock()
            return
        }
        closed = true
        waiter = pending
        pending = nil
        lock.unlock()
        waiter?.resume(returning: nil)
    }

    /// The next delivered result, or `nil` once the channel is closed and drained.
    /// At most one consumer at a time (the load's serial merge loop).
    func next() async -> T? {
        await withCheckedContinuation { (cont: CheckedContinuation<T?, Never>) in
            lock.lock()
            if !queue.isEmpty {
                let value = queue.removeFirst()
                lock.unlock()
                cont.resume(returning: value)
                return
            }
            if closed {
                lock.unlock()
                cont.resume(returning: nil)
                return
            }
            pending = cont
            lock.unlock()
        }
    }
}
