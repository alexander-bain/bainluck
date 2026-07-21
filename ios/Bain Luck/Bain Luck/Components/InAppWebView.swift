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
    let url: URL

    #if canImport(WebKit)
    @State private var isLoading = true

    var body: some View {
        ZStack {
            WebViewRepresentable(url: url, isLoading: $isLoading)
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

#if canImport(WebKit)
private struct WebViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool

    func makeCoordinator() -> Coordinator { Coordinator(isLoading: $isLoading) }

    final class Coordinator: NSObject, WKNavigationDelegate {
        @Binding var isLoading: Bool
        init(isLoading: Binding<Bool>) { _isLoading = isLoading }

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
