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
    var interceptHandOff: ((URL) -> Bool)? = nil
    var scrollFooter: AnyView? = nil

    #if canImport(WebKit)
    @Environment(\.openURL) private var openURL
    @State private var isLoading = true

    var body: some View {
        ZStack {
            WebViewRepresentable(
                url: url,
                linkPolicy: linkPolicy,
                isLoading: $isLoading,
                scrollFooter: scrollFooter,
                handOff: { candidate in
                    if interceptHandOff?(candidate) == true {
                        return
                    }
                    openURL(candidate)
                }
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
            Button("Open \(url.host ?? "page")") {
                if interceptHandOff?(url) == true {
                    return
                }
                openURL(url)
            }
            .buttonStyle(.borderedProminent)
            if let scrollFooter {
                scrollFooter
            }
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

    /// `true` when an outgoing link points to Bain Luck's own `/discover` feed
    /// (such as the "Start exploring" button at the bottom of `/about`), which
    /// the app opens natively on the Discover tab instead of ejecting to Safari.
    static func opensDiscoverInApp(_ candidate: URL) -> Bool {
        guard isWeb(candidate), siteHost(candidate) == "bainluck.com" else { return false }
        return normalizedPath(candidate) == "/discover"
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

    /// A bare origin has the empty path, and the empty path is `/`.
    ///
    /// There WAS a trailing-slash trim here, so that `/about/` and `/about`
    /// read alike. It is gone because the mutation battery could not kill it:
    /// `URL.path` already drops a trailing slash, so the branch was unreachable
    /// for every input this function can receive, and unreachable code that
    /// looks like a rule is worse than no code — it invites the next reader to
    /// believe the normalisation is ours to change. The `/about/` case keeps
    /// its test; what the test now pins is Foundation's behaviour, which is
    /// exactly what would break if this ever moved to `path(percentEncoded:)`
    /// or `pathComponents`.
    private static func normalizedPath(_ url: URL) -> String {
        let path = url.path
        return path.isEmpty ? "/" : path
    }
}

#if canImport(WebKit)
private struct WebViewRepresentable {
    let url: URL
    let linkPolicy: InAppWebView.LinkPolicy
    @Binding var isLoading: Bool
    var scrollFooter: AnyView? = nil
    let handOff: (URL) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url, linkPolicy: linkPolicy, isLoading: $isLoading, handOff: handOff)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let url: URL
        private let linkPolicy: InAppWebView.LinkPolicy
        private let handOff: (URL) -> Void
        @Binding var isLoading: Bool
        private var hasFinishedInitialLoad = false

        #if !os(macOS)
        private var footerHost: UIHostingController<AnyView>?
        private var contentSizeObservation: NSKeyValueObservation?
        private var boundsObservation: NSKeyValueObservation?
        private var isLayingOutFooter = false
        #endif

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
            hasFinishedInitialLoad = true
            #if !os(macOS)
            layoutFooter(in: webView)
            #endif
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            isLoading = false
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            isLoading = false
        }

        #if !os(macOS)
        func configureScrollFooter(_ footer: AnyView?, in webView: WKWebView) {
            guard let footer else {
                footerHost?.view.removeFromSuperview()
                footerHost = nil
                contentSizeObservation = nil
                boundsObservation = nil
                if webView.scrollView.contentInset.bottom != 0 {
                    webView.scrollView.contentInset.bottom = 0
                    webView.scrollView.verticalScrollIndicatorInsets.bottom = 0
                }
                return
            }

            if let existing = footerHost {
                existing.rootView = footer
                layoutFooter(in: webView)
                return
            }

            let host = UIHostingController(rootView: footer)
            host.view.backgroundColor = .clear
            host.view.isHidden = true
            host.view.accessibilityIdentifier = "in-app-webview-scroll-footer"
            webView.scrollView.addSubview(host.view)
            footerHost = host

            contentSizeObservation = webView.scrollView.observe(\.contentSize, options: [.new]) { [weak self, weak webView] _, _ in
                guard let self, let webView else { return }
                self.layoutFooter(in: webView)
            }
            boundsObservation = webView.scrollView.observe(\.bounds, options: [.new]) { [weak self, weak webView] _, _ in
                guard let self, let webView else { return }
                self.layoutFooter(in: webView)
            }
            layoutFooter(in: webView)
        }

        func layoutFooter(in webView: WKWebView) {
            guard !isLayingOutFooter, let host = footerHost else { return }
            let width = max(webView.scrollView.bounds.width, webView.bounds.width)
            let contentHeight = webView.scrollView.contentSize.height
            guard hasFinishedInitialLoad, width > 0, contentHeight > 0 else {
                host.view.isHidden = true
                return
            }
            isLayingOutFooter = true
            defer { isLayingOutFooter = false }

            host.view.isHidden = false
            let fitted = host.sizeThatFits(
                in: CGSize(width: width, height: UIView.layoutFittingCompressedSize.height)
            )
            let footerHeight = ceil(max(fitted.height, 44))
            if abs(webView.scrollView.contentInset.bottom - footerHeight) > 0.5 {
                webView.scrollView.contentInset.bottom = footerHeight
                webView.scrollView.verticalScrollIndicatorInsets.bottom = footerHeight
            }
            let targetFrame = CGRect(x: 0, y: contentHeight, width: width, height: footerHeight)
            if host.view.frame != targetFrame {
                host.view.frame = targetFrame
            }
        }
        #endif
    }
}

#if os(macOS)
extension WebViewRepresentable: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        if scrollFooter != nil {
            let scriptSource = """
            (function() {
                if (document.getElementById('in-app-webview-scroll-footer')) return;
                var row = document.createElement('a');
                row.id = 'in-app-webview-scroll-footer';
                row.href = 'https://www.bainluck.com/picture-credits';
                row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-top:1px solid rgba(0,0,0,0.1);text-decoration:none;color:inherit;font-size:15px;font-weight:500;';
                row.innerHTML = '<span>Picture credits</span><span style="opacity:0.6;font-size:12px;">↗</span>';
                document.body.appendChild(row);
            })();
            """
            config.userContentController.addUserScript(
                WKUserScript(source: scriptSource, injectionTime: .atDocumentEnd, forMainFrameOnly: true)
            )
        }
        let webView = WKWebView(frame: .zero, configuration: config)
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
        context.coordinator.configureScrollFooter(scrollFooter, in: webView)
        webView.load(URLRequest(url: url))
        return webView
    }
    func updateUIView(_ uiView: WKWebView, context: Context) {
        context.coordinator.configureScrollFooter(scrollFooter, in: uiView)
    }
}
#endif
#endif
