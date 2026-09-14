import SwiftUI

/// Native About screen — a clean in-app web view of the canonical /about story
/// (L2-144 Item 3, Alex's ask; "clean webview of /about is acceptable v1").
///
/// Rendering the live /about keeps the app's About in lockstep with the
/// single-source narrative rebuilt in L2-143 (one-liner → anti-thesis → the
/// blend + live calibration proof → the story thesis + two case studies → the
/// human line) — there is no separate native copy to drift. Reachable from the
/// My Stuff profile hub and the Preferences settings screen.
struct AboutView: View {
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
    private static let aboutURL = URL(string: "https://www.bainluck.com/about?embed=1")!

    var body: some View {
        // `.handOffToTheSystem` (the default, named here because it is load-
        // bearing rather than incidental): the About copy links to
        // /calibration, /privacy, /discover and mailto:bugs@bainluck.com. Left
        // to follow in place, one tap turns a screen titled "About" into a
        // second copy of the website — which is the defect #5914 is about,
        // arriving a moment later. Those links now open in Safari and Mail.
        InAppWebView(url: Self.aboutURL, linkPolicy: .handOffToTheSystem)
            .navigationTitle("About")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }
}
