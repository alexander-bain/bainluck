import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

extension Notification.Name {
    static let deviceDidShake = Notification.Name("deviceDidShake")
}

#if os(iOS)
extension UIWindow {
    open override func motionEnded(_ motion: UIEvent.EventSubtype, with event: UIEvent?) {
        if motion == .motionShake {
            NotificationCenter.default.post(name: .deviceDidShake, object: nil)
        }
        super.motionEnded(motion, with: event)
    }
}
#endif
