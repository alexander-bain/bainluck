import Combine
import Foundation
import SwiftUI

/// Reader's liked Discover cards, scoped per signed-in account (#13769, 420: D).
///
/// Survives scrolling offscreen/back within a session and across launches for the
/// same account. Tapping a filled `"Liked"` heart removes it locally here without
/// ever emitting `.unlike` (which teaches "less like this" on the server).
@MainActor
final class DiscoverLikedStore420D: ObservableObject {
    static let storageKeyPrefix = "discover_liked_items_420d"

    @Published private(set) var likedKeys: Set<String>

    private let defaults: UserDefaults
    private var accountKey: String

    init(userId: String? = nil, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let initialAccount = Self.storageKey(for: userId)
        self.accountKey = initialAccount
        let stored = defaults.stringArray(forKey: initialAccount) ?? []
        self.likedKeys = Set(stored)
    }

    static func storageKey(for userId: String?) -> String {
        let trimmed = userId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? "\(storageKeyPrefix):guest" : "\(storageKeyPrefix):\(trimmed)"
    }

    func syncAccount(userId: String?) {
        let nextKey = Self.storageKey(for: userId)
        guard nextKey != accountKey else { return }
        accountKey = nextKey
        let stored = defaults.stringArray(forKey: nextKey) ?? []
        likedKeys = Set(stored)
    }

    func isLiked(_ itemKey: String) -> Bool {
        likedKeys.contains(itemKey)
    }

    /// Marks `itemKey` as liked. Returns `true` only if it was not already liked
    /// so repeated right swipes stay idempotent without duplicating `.like` writes.
    @discardableResult
    func markLiked(_ itemKey: String) -> Bool {
        guard !likedKeys.contains(itemKey) else { return false }
        likedKeys.insert(itemKey)
        persist()
        return true
    }

    /// Removes the local like without emitting `.unlike` (#13769).
    func unmarkLiked(_ itemKey: String) {
        guard likedKeys.remove(itemKey) != nil else { return }
        persist()
    }

    private func persist() {
        defaults.set(Array(likedKeys).sorted(), forKey: accountKey)
    }
}

/// Action & share metadata injected by `DiscoverView` for every card inside Discover.
struct DiscoverCardLikeAction420D {
    let itemKey: String
    let isLiked: Bool
    let pinType: String?
    let pinId: Int?
    let shareURL: URL?
    let shareTitle: String?
    let shareMessage: String?
    let onToggle: () -> Void
    let onShare: (() -> Void)?

    init(
        itemKey: String,
        isLiked: Bool,
        pinType: String? = nil,
        pinId: Int? = nil,
        shareURL: URL? = nil,
        shareTitle: String? = nil,
        shareMessage: String? = nil,
        onToggle: @escaping () -> Void,
        onShare: (() -> Void)? = nil
    ) {
        self.itemKey = itemKey
        self.isLiked = isLiked
        self.pinType = pinType
        self.pinId = pinId
        self.shareURL = shareURL
        self.shareTitle = shareTitle
        self.shareMessage = shareMessage
        self.onToggle = onToggle
        self.onShare = onShare
    }
}

private struct DiscoverCardLikeAction420DKey: EnvironmentKey {
    static let defaultValue: DiscoverCardLikeAction420D? = nil
}

extension EnvironmentValues {
    var discoverCardLikeAction420D: DiscoverCardLikeAction420D? {
        get { self[DiscoverCardLikeAction420DKey.self] }
        set { self[DiscoverCardLikeAction420DKey.self] = newValue }
    }
}

/// Pure transition table for #13769 (420: D) so tests verify every side effect
/// of right-swipe, heart-like, heart-undo, and left-swipe without a live network.
nonisolated enum DiscoverLikeFeedbackRule420D {
    struct Resolution: Equatable, Sendable {
        let shouldHideCard: Bool
        let nextLikedState: Bool
        let emittedAction: String?
    }

    static func resolveRightSwipe(wasLiked: Bool) -> Resolution {
        Resolution(
            shouldHideCard: false,
            nextLikedState: true,
            emittedAction: wasLiked ? nil : "like"
        )
    }

    static func resolveHeartTap(wasLiked: Bool) -> Resolution {
        if wasLiked {
            // Undo removes the heart locally and NEVER sends `unlike`.
            return Resolution(
                shouldHideCard: false,
                nextLikedState: false,
                emittedAction: nil
            )
        } else {
            return Resolution(
                shouldHideCard: false,
                nextLikedState: true,
                emittedAction: "like"
            )
        }
    }

    static func resolveLeftSwipe() -> Resolution {
        Resolution(
            shouldHideCard: true,
            nextLikedState: false,
            emittedAction: "unlike"
        )
    }
}
