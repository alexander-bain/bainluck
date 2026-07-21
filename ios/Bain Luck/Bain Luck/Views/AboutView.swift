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
    private static let aboutURL = URL(string: "https://bainluck.com/about")!

    var body: some View {
        InAppWebView(url: Self.aboutURL)
            .navigationTitle("About")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .onAppear { AnalyticsService.trackScreen(name: "about", type: "about") }
    }
}
