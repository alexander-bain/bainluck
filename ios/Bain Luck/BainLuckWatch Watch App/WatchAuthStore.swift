import Foundation

// MARK: - Watch Auth Store
//
// The watch app has no sign-in flow of its own (OAuth popups can't run on the
// wrist). Favorite teams are stored server-side per authenticated user, so the
// "my teams" strip only lights up when a Bearer token is available.
//
// This store is the single integration seam for that token: it reads from a
// shared UserDefaults key that a future phone→watch WatchConnectivity bridge
// will populate (the paired iPhone is already signed in). Until that bridge
// lands, `token` is nil and the home glance shows a graceful signed-out state
// for the my-teams section — the marquee top story does not depend on auth.

nonisolated struct WatchAuthStore: Sendable {
    static let shared = WatchAuthStore()

    /// Key written by the phone→watch token bridge (WatchConnectivity, follow-up).
    static let tokenKey = "bainluck_watch_auth_token"

    private init() {}

    /// The current session Bearer token, or nil when the watch is signed out.
    var token: String? {
        guard let raw = UserDefaults.standard.string(forKey: Self.tokenKey),
              !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return raw
    }

    var isSignedIn: Bool { token != nil }
}
