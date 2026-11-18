import Foundation

extension Notification.Name {
    static let groupingMachineryGateDidChange12288 = Notification.Name("BainLuck.GroupingMachineryGateDidChange12288")
}

/// Double-gate authority for `#12288` grouping machinery preview on iPhone:
/// 1. Server gate: `/api/containers/preview/machinery` and `/api/containers/machinery-*`
///    require authenticated admin credentials (`_check_admin_auth`).
/// 2. Client owner-only gate: only the owner account (`id == 364`)
///    can see the Preferences switch, which defaults strictly to `false` (`off`).
///    Public, signed-out, and non-owner accounts never see the switch, see nothing on
///    Discover or container routes, and issue zero machinery network requests.
enum GroupingMachineryGate12288 {
    static let ownerUserId: Int = 364

    private static let keyPrefix = "bainluck_owner_grouping_machinery_preview_"
    private static let lock = NSLock()
    private nonisolated(unsafe) static var _activeUser: AuthUser?
    private nonisolated(unsafe) static var _overrideDefaults: UserDefaults?

    /// Updates the currently signed-in profile observed by non-view callers (`APIClient`,
    /// `ContainerHubViewModel`). Passing `nil` on sign-out immediately revokes access.
    nonisolated static func setActiveUser(_ user: AuthUser?) {
        lock.lock()
        _activeUser = user
        lock.unlock()
        NotificationCenter.default.post(name: .groupingMachineryGateDidChange12288, object: nil)
    }

    nonisolated static var activeUser: AuthUser? {
        lock.lock()
        defer { lock.unlock() }
        return _activeUser
    }

    /// Test seam allowing XCTests to isolate `UserDefaults` without mutating `.standard`.
    nonisolated static func setOverrideDefaultsForTesting(_ defaults: UserDefaults?) {
        lock.lock()
        _overrideDefaults = defaults
        lock.unlock()
    }

    private nonisolated static var effectiveDefaults: UserDefaults {
        lock.lock()
        defer { lock.unlock() }
        return _overrideDefaults ?? .standard
    }

    /// True ONLY for the owner account (`id == 364`).
    nonisolated static func isOwnerUser(_ user: AuthUser?) -> Bool {
        guard let user else { return false }
        return user.id == ownerUserId
    }

    nonisolated static func storageKey(for user: AuthUser) -> String {
        "\(keyPrefix)\(user.id)"
    }

    /// Reads the owner-only Preferences switch (`false` by default; always `false` for non-owners).
    nonisolated static func isSwitchEnabled(
        for user: AuthUser?,
        defaults: UserDefaults? = nil
    ) -> Bool {
        guard let user, isOwnerUser(user) else { return false }
        let store = defaults ?? effectiveDefaults
        return store.bool(forKey: storageKey(for: user))
    }

    /// Updates the owner-only Preferences switch. Ignored for nil or non-owner accounts.
    nonisolated static func setSwitchEnabled(
        _ enabled: Bool,
        for user: AuthUser?,
        defaults: UserDefaults? = nil
    ) {
        guard let user, isOwnerUser(user) else { return }
        let store = defaults ?? effectiveDefaults
        store.set(enabled, forKey: storageKey(for: user))
        NotificationCenter.default.post(name: .groupingMachineryGateDidChange12288, object: nil)
    }

    /// True iff `user` is Alex AND the Preferences switch is explicitly turned `on`.
    nonisolated static func canAccessMachinery(
        user: AuthUser?,
        defaults: UserDefaults? = nil
    ) -> Bool {
        isOwnerUser(user) && isSwitchEnabled(for: user, defaults: defaults)
    }

    /// Convenience check against the active session user (`AuthManager.user`).
    nonisolated static func canAccessMachineryCurrentUser(defaults: UserDefaults? = nil) -> Bool {
        canAccessMachinery(user: activeUser, defaults: defaults)
    }

    /// True when `slug` names a `machinery-*` candidate grouping.
    nonisolated static func isMachineryCandidateSlug(_ slug: String) -> Bool {
        slug.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .hasPrefix("machinery-")
    }
}
