import Foundation

/// Retains only an undelivered tap, never a background scene's navigation.
/// The scene supplies window opening; this helper owns no window or service.
final class MacNotificationDelivery10878 {
    static let primaryWindowID = "mac-browsing"
    @MainActor static let shared = MacNotificationDelivery10878()

    @MainActor private weak var navigation: NavigationCoordinator?
    @MainActor private var pending: NotificationManager.NotificationDestination?
    @MainActor private var requestWindow: (@MainActor () -> Void)?

    @MainActor
    func bind(_ navigation: NavigationCoordinator?, permitsBrowsing: Bool) {
        // A game window or inactive scene must clear the former target. A tap
        // arriving afterward waits for the primary browsing window to bind.
        self.navigation = permitsBrowsing ? navigation : nil
        deliverPendingIfPossible()
    }

    @MainActor
    func receive(_ destination: NotificationManager.NotificationDestination) {
        guard destination != .none else { return }
        pending = destination
        if navigation != nil {
            deliverPendingIfPossible()
        } else {
            requestWindow?()
        }
    }

    @MainActor
    func installWindowRequest(_ request: @escaping @MainActor () -> Void) {
        requestWindow = request
        if pending != nil, navigation == nil {
            request()
        }
    }

    @MainActor
    private func deliverPendingIfPossible() {
        guard let navigation, let destination = pending else { return }
        // Clear before dispatch: publication can synchronously cause another
        // bind or receive. Neither may replay this tap into another scene.
        pending = nil
        switch destination {
        case .labeling:
            navigation.navigate(to: .discoverLabeling, tab: .feed)
        case .url(let url):
            _ = navigation.handleURL(url)
        case .event(let id):
            navigation.navigate(to: .eventDetail(id: id), tab: .feed)
        case .market(let id):
            navigation.navigate(to: .futuresDetail(id: id), tab: .feed)
        case .none:
            break
        }
    }
}
