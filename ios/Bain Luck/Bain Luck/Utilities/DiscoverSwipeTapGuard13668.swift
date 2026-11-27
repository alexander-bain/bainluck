import Foundation
import SwiftUI

/// Suppresses accidental inner-card taps during and right after a horizontal
/// swipe gesture on Discover grouped cards (#13668 / #7074).
final class DiscoverSwipeTapGuard13668: @unchecked Sendable {
    private let lock = NSLock()
    private var isDraggingHorizontally = false
    private var suppressTapsUntil: Date = .distantPast
    private let cancelCooldown: TimeInterval
    private let commitCooldown: TimeInterval
    private let clock: @Sendable () -> Date

    init(
        cancelCooldown: TimeInterval = 0.25,
        commitCooldown: TimeInterval = 0.5,
        clock: @escaping @Sendable () -> Date = Date.init
    ) {
        self.cancelCooldown = cancelCooldown
        self.commitCooldown = commitCooldown
        self.clock = clock
    }

    func beginHorizontalDrag() {
        lock.lock()
        isDraggingHorizontally = true
        lock.unlock()
    }

    func endHorizontalDrag(committed: Bool) {
        let now = clock()
        let duration = committed ? commitCooldown : cancelCooldown
        let until = now.addingTimeInterval(duration)
        lock.lock()
        isDraggingHorizontally = false
        if until > suppressTapsUntil {
            suppressTapsUntil = until
        }
        lock.unlock()
    }

    func cancel() {
        lock.lock()
        isDraggingHorizontally = false
        lock.unlock()
    }

    func allowsTap() -> Bool {
        let now = clock()
        lock.lock()
        let allowed = !isDraggingHorizontally && now >= suppressTapsUntil
        lock.unlock()
        return allowed
    }
}

private struct DiscoverSwipeTapGuard13668Key: EnvironmentKey {
    static let defaultValue: DiscoverSwipeTapGuard13668? = nil
}

extension EnvironmentValues {
    var discoverSwipeTapGuard13668: DiscoverSwipeTapGuard13668? {
        get { self[DiscoverSwipeTapGuard13668Key.self] }
        set { self[DiscoverSwipeTapGuard13668Key.self] = newValue }
    }
}
