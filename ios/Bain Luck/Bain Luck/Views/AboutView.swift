import SwiftUI

/// Native About screen — a clean in-app web view of the canonical /about story
/// (L2-144 Item 3, Alex's ask; "clean webview of /about is acceptable v1"), paired
/// with a native "Picture credits" link to the website's `/picture-credits` page
/// (Ruling 195-A / #12659).
///
/// Rendering the live /about keeps the app's About in lockstep with the
/// single-source narrative rebuilt in L2-143 (one-liner → anti-thesis → the
/// blend + live calibration proof → the story thesis + two case studies → the
/// human line) — there is no separate native copy to drift. Reachable from the
/// My Stuff profile hub and the Preferences settings screen.
struct AboutView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @Environment(\.dismiss) private var dismiss

    /// `?embed=1` is the native half of the #5914 embed contract, agreed with
    /// ux 2026-09-14: on `/about`, and only on `/about`, it tells the page it is
    /// being rendered inside the app, so the site drops the chrome that has no
    /// business on an app screen — a second header carrying the WEBSITE's "Sign
    /// in" button, a second tab bar drawn over the real one, and a cookie
    /// consent banner for tracking the embed does not load.
    ///
    /// A query parameter rather than a `customUserAgent` (the issue offered
    /// both) for three reasons: the page reads it with `useSearchParams()`,
    /// where a user-agent marker would need a `headers()` read in the root
    /// layout and make every route on the site dynamic; it is reproducible
    /// outside the app, so `tools/look.sh` and a desktop browser can both see
    /// what a reviewer sees; and `git grep embed=1` finds both halves.
    ///
    /// `www`, not the apex: the apex 307s here (measured, and the frontend's own
    /// `getSiteUrl()` says the same), and this screen has no budget for a
    /// redirect hop it can skip. `InAppWebViewNavigation` treats the two hosts
    /// as one site regardless, so the apex form would still render in place.
    static let aboutURL = URL(string: "https://www.bainluck.com/about?embed=1")!

    /// Ruling 195-A (#12659): opens the website's Picture credits page
    /// (`/picture-credits`, coordinated with Atlas PR #12732) in the system browser.
    static let pictureCreditsURL = URL(string: "https://www.bainluck.com/picture-credits")!

    /// Intercepts the "Start exploring" CTA (`/discover`) at the bottom of `/about`
    /// so tapping it switches natively to the Discover tab instead of leaving the
    /// app for Safari, while `/calibration`, `/privacy`, `/picture-credits`, and
    /// `mailto:` still hand off to the system.
    static func handleOutgoingLink(
        _ candidate: URL,
        navigation: NavigationCoordinator,
        dismiss: () -> Void
    ) -> Bool {
        guard InAppWebViewNavigation.opensDiscoverInApp(candidate) else {
            return false
        }
        dismiss()
        navigation.selectedTab = .discover
        return true
    }

    var body: some View {
        // `.handOffToTheSystem` (the default, named here because it is load-
        // bearing rather than incidental): the About copy links to
        // /calibration, /privacy, /picture-credits, /discover and
        // mailto:bugs@bainluck.com. Left to follow in place, one tap turns a
        // screen titled "About" into a second copy of the website — which is
        // the defect #5914 is about, arriving a moment later. /discover switches
        // natively to the Discover tab; the remaining outgoing links open in
        // Safari and Mail.
        VStack(spacing: 0) {
            InAppWebView(
                url: Self.aboutURL,
                linkPolicy: .handOffToTheSystem,
                interceptHandOff: { candidate in
                    Self.handleOutgoingLink(
                        candidate,
                        navigation: navCoordinator,
                        dismiss: { dismiss() }
                    )
                }
            )
            Divider()
            Link(destination: Self.pictureCreditsURL) {
                HStack(spacing: 8) {
                    Text("Picture credits")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.primary)
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 13)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.cardBackground)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("about-picture-credits-link")
        }
        .navigationTitle("About")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }
}
