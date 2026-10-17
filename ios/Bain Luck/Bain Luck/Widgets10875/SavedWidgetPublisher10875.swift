import SwiftUI
#if canImport(WidgetKit)
import WidgetKit
#endif

/// #10875 — the app half of the widget bridge: whenever the pin manager's
/// account or saved set changes, write the snapshot to the app group and ask
/// WidgetKit to reload the saved-item widgets.
///
/// Everything here runs synchronously on the main actor against the pin
/// manager's state at that instant, and `boundUserID` and `savedPins` change
/// together inside `PinManager.bindAccount`. There is no asynchronous callback
/// that could land after an account switch and republish the previous
/// account's set.
extension SavedWidgetSnapshot10875 {
    /// The pins the manager holds for the account it is bound to. A guest's
    /// pins are the device's own, so they count as confirmed.
    static func from(boundUserID: String?, savedPins: [SavedPin], loadState: PinLoadState) -> Self {
        Self(scope: SavedWidgetBridge10875.scope(userID: boundUserID),
             subjects: savedPins.compactMap { SavedWidgetSubject10875(pinType: $0.type, value: $0.value) },
             pinsConfirmed: boundUserID == nil || loadState == .loaded)
    }
}

struct SavedWidgetPublisher10875 {
    let store: SavedWidgetBridgeStore10875?
    let reload: () -> Void

    /// Writes a changed snapshot and asks for a reload. A reload request is
    /// not a refresh: WidgetKit decides when the widgets run.
    func publish(_ snapshot: SavedWidgetSnapshot10875) {
        guard let store, store.write(snapshot) else { return }
        reload()
    }

    static let live = SavedWidgetPublisher10875(
        store: SavedWidgetBridge10875.sharedDefaults.map(SavedWidgetBridgeStore10875.init),
        reload: {
            #if canImport(WidgetKit)
            WidgetCenter.shared.reloadTimelines(ofKind: SavedWidgetBridge10875.widgetKind)
            #endif
        }
    )
}

private struct SavedItemWidgetsModifier10875: ViewModifier {
    @ObservedObject var pins: PinManager
    let publisher: SavedWidgetPublisher10875

    func body(content: Content) -> some View {
        content
            .task { publish() }
            .onChange(of: snapshot) { _, _ in publish() }
    }

    private var snapshot: SavedWidgetSnapshot10875 {
        .from(boundUserID: pins.boundUserID, savedPins: pins.savedPins, loadState: pins.loadState)
    }

    private func publish() {
        #if DEBUG
        // The #9875 rig's fixture accounts are not the reader's.
        if PinManagementRuntime9875.shared != nil { return }
        #endif
        publisher.publish(snapshot)
    }
}

extension View {
    /// #10875 — keeps the Home/Lock Screen widget's view of the saved items
    /// and their account in step with the pin manager.
    func savedItemWidgets10875(pins: PinManager, publisher: SavedWidgetPublisher10875 = .live) -> some View {
        modifier(SavedItemWidgetsModifier10875(pins: pins, publisher: publisher))
    }
}
