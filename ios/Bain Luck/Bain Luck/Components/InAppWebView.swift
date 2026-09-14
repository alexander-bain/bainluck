import SwiftUI
#if canImport(WebKit)
import WebKit
#endif

/// A lightweight in-app web view (WKWebView) with a loading indicator, used to
/// surface canonical web surfaces natively — e.g. the /about story (L2-144 Item 3,
/// "clean webview of /about is acceptable v1"). Cross-platform: WKWebView is
/// available on iOS / iPadOS / macOS. On any platform without WebKit it falls
/// back to an openURL button so the screen still compiles and functions.
///
/// Named `InAppWebView` (not `WebView`) to avoid ambiguity with WebKit's legacy
/// `WebView` class on macOS.
struct InAppWebView: View {
    /// What this web view does when the page it is showing tries to navigate
    /// somewhere else.
    ///
    /// This exists because of #5914. The About screen is one page of the site
    /// rendered inside an app screen whose navigation bar says "About"; a link
    /// followed in place leaves that title lying about what is underneath it,
    /// and — until the embed contract lands — brings the whole site shell back
    /// with it. A screen that silently becomes a browser is the defect, not the
    /// remedy for it.
    enum LinkPolicy {
        /// Follow every navigation in place. This web view is a browser.
        case followInPlace

        /// Render only `url` itself. Any other navigation the page starts is
        /// cancelled here and handed to the system — Safari for a web link,
        /// Mail for a `mailto:`.
        ///
        /// The default, because both of the things this component is for (a
        /// canonical page shown under a native title) want it, and because the
        /// failure mode of the other choice is silent.
        case handOffToTheSystem
    }

    let url: URL
    var linkPolicy: LinkPolicy = .handOffToTheSystem

    #if canImport(WebKit)
    @Environment(\.openURL) private var openURL
    @State private var isLoading = true

    var body: some View {
        ZStack {
            WebViewRepresentable(
                url: url,
                linkPolicy: linkPolicy,
                isLoading: $isLoading,
                handOff: { openURL($0) }
            )
            if isLoading {
                ProgressView()
            }
        }
    }
    #else
    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(spacing: 16) {
            Text("Open in your browser").font(.headline)
            Button("Open \(url.host ?? "page")") { openURL(url) }
                .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    #endif
}

/// The decision half of `InAppWebView.LinkPolicy`, as a pure function of two
/// URLs.
///
/// Deliberately outside every `#if`: WebKit is not needed to answer "is this
/// the page we are embedding?", and a rule that only compiles on the WebKit
/// branch is a rule the iOS test target could still run but the macOS one
/// could not, which is how `#if os(macOS)` code goes unexercised.
enum InAppWebViewNavigation {

    /// `true` ⇒ load it here. `false` ⇒ cancel and hand it to the system.
    static func rendersInPlace(
        _ candidate: URL,
        embedding embedded: URL,
        under policy: InAppWebView.LinkPolicy
    ) -> Bool {
        switch policy {
        case .followInPlace:
            return true
        case .handOffToTheSystem:
            return isTheSamePage(candidate, embedded)
        }
    }

    /// Same site, same path. Query and fragment are deliberately ignored.
    ///
    /// Ignoring them is the fail-safe direction: `/about#calibration`,
    /// `/about` after a reload that drops `?embed=1`, and `/about/` are all the
    /// page the reader is already on, and ejecting them to Safari would be a
    /// worse defect than the one this rule exists to prevent — the reader would
    /// watch their own About screen launch a browser onto itself.
    private static func isTheSamePage(_ candidate: URL, _ embedded: URL) -> Bool {
        guard isWeb(candidate), isWeb(embedded) else { return false }
        guard let candidateHost = siteHost(candidate),
              let embeddedHost = siteHost(embedded),
              candidateHost == embeddedHost
        else { return false }
        return normalizedPath(candidate) == normalizedPath(embedded)
    }

    /// A `mailto:` — the About page has one, to bugs@bainluck.com — has no host
    /// and is never the page we are embedding. It is also the reason this
    /// function does not simply compare hosts: WKWebView cancels a scheme it
    /// cannot handle and reports nothing, so that link did nothing at all when
    /// tapped inside the app. Routed to the system it opens Mail.
    private static func isWeb(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased() else { return false }
        return scheme == "http" || scheme == "https"
    }

    /// `bainluck.com` and `www.bainluck.com` are one site.
    ///
    /// Not a nicety: the apex 307s to the `www` host (measured 2026-09-14), so
    /// a page asked for on one can legitimately finish loading on the other,
    /// and a strict host comparison would hand the About screen's own redirect
    /// to Safari. `NavigationCoordinator.handleURL` already treats the pair as
    /// one site for universal links; this is that rule, in the one other place
    /// we compare a URL to our own.
    private static func siteHost(_ url: URL) -> String? {
        guard let host = url.host?.lowercased(), !host.isEmpty else { return nil }
        return host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
    }

    /// `/about` and `/about/` are the same page; `""` (a bare origin) is `/`.
    private static func normalizedPath(_ url: URL) -> String {
        let path = url.path
        guard !path.isEmpty else { return "/" }
        guard path.count > 1, path.hasSuffix("/") else { return path }
        return String(path.dropLast())
    }
}

#if canImport(WebKit)
private struct WebViewRepresentable {
    let url: URL
    let linkPolicy: InAppWebView.LinkPolicy
    @Binding var isLoading: Bool
    let handOff: (URL) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url, linkPolicy: linkPolicy, isLoading: $isLoading, handOff: handOff)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let url: URL
        private let linkPolicy: InAppWebView.LinkPolicy
        private let handOff: (URL) -> Void
        @Binding var isLoading: Bool

        init(
            url: URL,
            linkPolicy: InAppWebView.LinkPolicy,
            isLoading: Binding<Bool>,
            handOff: @escaping (URL) -> Void
        ) {
            self.url = url
            self.linkPolicy = linkPolicy
            self.handOff = handOff
            _isLoading = isLoading
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let candidate = navigationAction.request.url else {
                decisionHandler(.allow)
                return
            }
            guard !InAppWebViewNavigation.rendersInPlace(candidate, embedding: url, under: linkPolicy) else {
                decisionHandler(.allow)
                return
            }
            decisionHandler(.cancel)
            // A cancelled navigation fires none of the didFail callbacks, so
            // the spinner would sit over the page forever if it happened to be
            // up when the reader tapped.
            isLoading = false
            handOff(candidate)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            isLoading = false
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            isLoading = false
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            isLoading = false
        }
    }
}

#if os(macOS)
extension WebViewRepresentable: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }
    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
#else
extension WebViewRepresentable: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
#endif
#endif
