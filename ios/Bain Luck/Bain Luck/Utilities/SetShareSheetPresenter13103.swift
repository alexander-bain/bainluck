import Foundation
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

/// #13103 — presents the system share sheet for a set URL (`bainluck.com/collections/<slug>`)
/// from a `.contextMenu` `Button` so the menu item both presents the native share UI
/// and fires its share instrumentation callback without adding uninstrumentable
/// `ShareLink` entries to `MENU_SITES` (#5525).
final class SetShareSheetPresenter13103 {
    static let shared = SetShareSheetPresenter13103()

    /// Test hook allowing unit tests to observe presented share URLs without opening UIKit modals.
    var testInterceptPresent: ((URL) -> Void)?

    func present(urlString: String) {
        let url = URL(string: urlString) ?? bainLuckFallbackURL
        present(url: url)
    }

    func present(url: URL) {
        if let intercept = testInterceptPresent {
            intercept(url)
            return
        }
        #if os(iOS)
        attemptPresentIOS(url: url, remainingRetries: 5)
        #elseif os(macOS)
        DispatchQueue.main.async {
            if let contentView = NSApp.keyWindow?.contentView {
                let picker = NSSharingServicePicker(items: [url])
                let anchor = NSRect(x: contentView.bounds.midX, y: contentView.bounds.midY, width: 1, height: 1)
                picker.show(relativeTo: anchor, of: contentView, preferredEdge: .minY)
            } else {
                copyToClipboard(url.absoluteString)
            }
        }
        #endif
    }

    #if os(iOS)
    private func attemptPresentIOS(url: URL, remainingRetries: Int) {
        // Hop off the immediate tap turn so UIKit's `.contextMenu` dismissal finishes
        // before presenting `UIActivityViewController` over the foreground window.
        let delay: TimeInterval = remainingRetries == 5 ? 0.05 : 0.12
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let host = Self.presentingHost() else {
                if remainingRetries > 0 {
                    self?.attemptPresentIOS(url: url, remainingRetries: remainingRetries - 1)
                }
                return
            }
            let activityVC = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            if let popover = activityVC.popoverPresentationController {
                popover.sourceView = host.view
                popover.sourceRect = CGRect(
                    x: host.view.bounds.midX,
                    y: host.view.bounds.midY,
                    width: 1,
                    height: 1
                )
                popover.permittedArrowDirections = []
            }
            host.present(activityVC, animated: true)
        }
    }

    /// Foreground-active scene's topmost non-dismissing controller (gotcha #27: Stage Manager).
    private static func presentingHost() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
            ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        guard let window = scene?.keyWindow ?? scene?.windows.first(where: \.isKeyWindow),
              var top = window.rootViewController else { return nil }
        while let presented = top.presentedViewController {
            if presented.isBeingDismissed { return nil }
            top = presented
        }
        return top.isBeingDismissed ? nil : top
    }
    #endif
}
