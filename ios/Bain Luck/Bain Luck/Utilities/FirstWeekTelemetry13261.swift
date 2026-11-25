import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// Pure classification & consent-safe session/arrival coordinator for `#13261`
/// first-week iPhone measurement (rows 6, 7, and 8; behind `"Allow"` / `181-C`).
///
/// Closed-enum discipline: every `source`, `medium`, `entryType`, `firstScreen`,
/// `destinationType`, and `relationType` collapses unknown free text to
/// `"unknown"` or `"other"` so user-entered URL params, names, or IDs never reach
/// telemetry.
nonisolated struct SharedLinkArrival13261: Equatable, Sendable {
    let entryType: String
    let destinationType: String
    let firstScreen: String
    let source: String
    let medium: String
}

nonisolated enum FirstWeekTelemetry13261 {
    static let allowedSources: Set<String> = [
        "share", "push", "email", "web", "app_clip", "qr", "social", "digest", "direct",
    ]
    static let allowedMediums: Set<String> = [
        "share_sheet", "morning_digest", "daily_digest", "smart_banner", "social", "web", "app_clip", "qr",
    ]
    static let allowedRelations: Set<String> = [
        "follow", "local", "alma_mater", "rival",
    ]

    /// Device-scoped, non-reversible keyed HMAC token (`404: B`) for string
    /// result identifiers such as tournament slugs so team/event/person names
    /// never leave the device.
    static func hashedResultId(_ raw: String) -> String {
        "h_\(AnalyticsPrivacy.hashQuery(raw))"
    }

    static func normalizedRelationType(_ raw: String) -> String {
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowedRelations.contains(lower) ? lower : "unknown"
    }

    static func normalizedSource(_ raw: String?) -> String {
        guard let raw else { return "unknown" }
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowedSources.contains(lower) ? lower : "unknown"
    }

    static func normalizedMedium(_ raw: String?) -> String {
        guard let raw else { return "unknown" }
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowedMediums.contains(lower) ? lower : "unknown"
    }

    /// Maps an opened universal or custom-scheme URL into closed categorical
    /// attribution tags. Widget deep links (`?source=widget`) return `nil` so they
    /// stay scoped exclusively to widget attribution rather than shared-link opens.
    static func classifyArrival(
        url: URL,
        destinationType: String,
        firstScreen: String
    ) -> SharedLinkArrival13261? {
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let queryItems = components?.queryItems ?? []
        let rawSource = queryItems.first(where: { $0.name == "source" || $0.name == "utm_source" })?.value
        if rawSource?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "widget" {
            return nil
        }

        let entryType = (url.scheme?.lowercased() == "bainluck") ? "custom_scheme" : "universal_link"
        let rawMedium = queryItems.first(where: { $0.name == "medium" || $0.name == "utm_medium" })?.value
        return SharedLinkArrival13261(
            entryType: entryType,
            destinationType: destinationType,
            firstScreen: firstScreen,
            source: normalizedSource(rawSource),
            medium: normalizedMedium(rawMedium)
        )
    }

    @MainActor
    static var currentSurface: String {
        #if os(macOS)
        return "macos"
        #elseif os(iOS)
        return UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone"
        #else
        return "ios"
        #endif
    }
}

/// Holds first-launch arrival metadata strictly in memory until `"Allow"`
/// consent (`181-C`) is verified, so Day-1 `session_open` & launch `shared_link_open`
/// fire once if granted and emit nothing if declined or unanswered.
@MainActor
final class SessionOpenTracker13261 {
    static let shared = SessionOpenTracker13261()

    private let isGranted: () -> Bool
    private let emitSessionOpen: (Bool, Int, String, String) -> Void
    private let emitSharedLinkOpen: (SharedLinkArrival13261) -> Void

    private var launchRecorded = false
    private var emittedSessionOpen = false
    private var pendingIsFirstSession = false
    private var pendingSessionNumber = 0
    private var pendingEntryType = "direct"
    private var pendingFirstScreen = "discover"
    private var pendingSharedLink: SharedLinkArrival13261?

    init(
        isGranted: @escaping () -> Bool = { TelemetryConsent.shared.isGranted },
        emitSessionOpen: @escaping (Bool, Int, String, String) -> Void = { isFirst, num, entry, screen in
            AnalyticsService.trackSessionOpen(
                isFirstSession: isFirst,
                sessionNumber: num,
                entryType: entry,
                firstScreen: screen
            )
        },
        emitSharedLinkOpen: @escaping (SharedLinkArrival13261) -> Void = { link in
            AnalyticsService.trackSharedLinkOpen(
                entryType: link.entryType,
                destinationType: link.destinationType,
                source: link.source,
                medium: link.medium
            )
        }
    ) {
        self.isGranted = isGranted
        self.emitSessionOpen = emitSessionOpen
        self.emitSharedLinkOpen = emitSharedLinkOpen
    }

    func recordLaunch(sessionNumber: Int) {
        launchRecorded = true
        pendingIsFirstSession = (sessionNumber <= 1)
        pendingSessionNumber = max(sessionNumber, 1)
        pendingEntryType = "direct"
        pendingFirstScreen = "discover"
        pendingSharedLink = nil

        if isGranted() {
            flushIfConsented()
        }
    }

    func recordArrival(_ arrival: SharedLinkArrival13261) {
        if launchRecorded && !emittedSessionOpen {
            pendingEntryType = arrival.entryType
            pendingFirstScreen = arrival.firstScreen
            pendingSharedLink = arrival
            if isGranted() {
                flushIfConsented()
            }
            return
        }

        if isGranted() {
            emitSharedLinkOpen(arrival)
        }
    }

    func handleConsentChange() {
        if isGranted() {
            flushIfConsented()
        } else {
            clearPending()
        }
    }

    func flushIfConsented() {
        guard isGranted(), launchRecorded, !emittedSessionOpen else { return }
        if let link = pendingSharedLink {
            emitSharedLinkOpen(link)
            pendingSharedLink = nil
        }
        emittedSessionOpen = true
        emitSessionOpen(
            pendingIsFirstSession,
            pendingSessionNumber,
            pendingEntryType,
            pendingFirstScreen
        )
    }

    func clearPending() {
        pendingSharedLink = nil
        launchRecorded = false
        emittedSessionOpen = false
    }

    func resetForTests() {
        clearPending()
        pendingIsFirstSession = false
        pendingSessionNumber = 0
        pendingEntryType = "direct"
        pendingFirstScreen = "discover"
    }
}
