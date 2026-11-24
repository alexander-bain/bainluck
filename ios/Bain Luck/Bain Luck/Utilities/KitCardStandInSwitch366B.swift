import Foundation

/// Resolution of a `kind == "roundup"` Discover card under the Kit v1 stand-in switch (`366: B` / `#13551`).
nonisolated enum DiscoverKitStandInResolution366B: Equatable, Sendable {
    /// Switch is ON (DEBUG/test only) and the payload carried a valid, non-refused `KitV1CardSpec`.
    case kit(KitV1CardSpec)
    /// Switch is OFF (always in Release and by default in Debug), or the kit card refused / failed closed.
    case standardCard
}

/// Ruling `366: B` / `363: A` (`#13551`) — Off-by-default stand-in switch allowing a `kit_card`
/// to stand in for today's Discover roundup/machinery card once blind-graded.
///
/// Safety guarantees:
/// - **Nothing reaches a reader:** `isEnabled` is hardcoded `false` in Release builds (`#else`)
///   and defaults to `false` in Debug builds unless the explicit `#if DEBUG` launch argument
///   `"-BainLuckEnableKitCardsPreview"` or a scoped XCTest override is active.
/// - **Fail-closed:** Even when switched on, any refused, unsupported (`kit_version != 1`),
///   or unrenderable `kit_card` resolves to `.standardCard` so Discover keeps rendering
///   today's card with real rows and real percents — never an empty card and never `0%`.
enum KitCardStandInSwitch366B {
    nonisolated static let defaultEnabled = false
    nonisolated static let debugLaunchArgument = "-BainLuckEnableKitCardsPreview"

    #if DEBUG
    private static let lock = NSLock()
    private nonisolated(unsafe) static var _testOverride: Bool?
    #endif

    /// Current effective state of the Discover Kit stand-in switch.
    /// Always `false` in Release builds and `false` by default in Debug builds.
    nonisolated static var isEnabled: Bool {
        #if DEBUG
        lock.lock()
        let overrideValue = _testOverride
        lock.unlock()
        if let overrideValue {
            return overrideValue
        }
        return ProcessInfo.processInfo.arguments.contains(debugLaunchArgument)
        #else
        return defaultEnabled
        #endif
    }

    #if DEBUG
    /// Scoped test hook for toggling the switch inside unit/render tests without persisting global state.
    @discardableResult
    nonisolated static func withOverrideForTesting<T>(
        _ enabled: Bool?,
        body: () throws -> T
    ) rethrows -> T {
        lock.lock()
        let previous = _testOverride
        _testOverride = enabled
        lock.unlock()
        defer {
            lock.lock()
            _testOverride = previous
            lock.unlock()
        }
        return try body()
    }
    #endif

    /// Resolves whether a Discover `roundup` item should render `KitCardView366B` or fall through
    /// to today's standard card (`MachineryDiscoverEntryCardView` / `DiscoverRoundupCardView`).
    nonisolated static func resolveDiscoverStandIn(
        contract: FeedRoundupContract?,
        isSwitchEnabled: Bool = KitCardStandInSwitch366B.isEnabled
    ) -> DiscoverKitStandInResolution366B {
        guard isSwitchEnabled,
              let spec = contract?.kitCardSpec,
              spec.body.isRenderable else {
            return .standardCard
        }
        switch spec.layout {
        case .stack, .grid, .calendar, .axis:
            return .kit(spec)
        }
    }

    /// Maps a `KitV1Route` emitted by `KitCardView366B` onto existing native navigation routes.
    static func resolveRoute(
        _ kitRoute: KitV1Route,
        fallbackCollectionRef: FeedThemeCollectionRef?,
        fallbackTitle: String
    ) -> Route? {
        switch kitRoute.kind {
        case .collection:
            let trimmedSlug = kitRoute.slug?.trimmingCharacters(in: .whitespacesAndNewlines)
            if let slug = trimmedSlug, !slug.isEmpty {
                if let ref = fallbackCollectionRef, ref.slug == slug {
                    return DiscoverGroupRows.collectionRoute(for: ref)
                }
                let displayName = (fallbackCollectionRef?.slug == slug ? fallbackCollectionRef?.name : nil)
                    ?? (!fallbackTitle.isEmpty ? fallbackTitle : slug)
                return .containerHub(slug: slug, name: displayName)
            }
            return fallbackCollectionRef.map { DiscoverGroupRows.collectionRoute(for: $0) }
        case .event:
            guard let id = kitRoute.id, id > 0 else { return nil }
            return .eventDetail(id: id)
        case .market:
            guard let id = kitRoute.id, id > 0 else { return nil }
            return .futuresDetail(id: id)
        case .team:
            guard let slug = kitRoute.slug?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !slug.isEmpty else {
                return nil
            }
            return .teamDetail(slug: slug)
        }
    }
}
