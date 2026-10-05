#if os(iOS) && canImport(ActivityKit)
import SwiftUI
import UIKit

/// Explicit foreground-only activity controls; never a background-live promise.
struct GameActivityControl: View {
    let snapshot: GameActivitySnapshot
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var controller = GameActivityController.shared

    private var presentation: GameActivityControlPresentation {
        GameActivityControlPresentation(
            isPhone: UIDevice.current.userInterfaceIdiom == .phone,
            isEnabled: controller.isEnabled,
            isTerminal: snapshot.isTerminal,
            isActive: controller.activeEventIDs.contains(snapshot.eventID))
    }

    var body: some View {
        Group {
            if presentation.showsControl {
                VStack(alignment: .leading, spacing: 6) {
                    if controller.activeEventIDs.contains(snapshot.eventID) {
                        Button("Stop Live Activity") {
                            Task { await controller.stop(eventID: snapshot.eventID) }
                        }
                        .accessibilityIdentifier("game.activity.stop")
                        .disabled(controller.isBusy)
                    } else {
                        Button("Start Live Activity") { controller.start(snapshot: snapshot) }
                            .accessibilityIdentifier("game.activity.start")
                            .disabled(controller.isBusy || snapshot.isTerminal
                                      || !controller.activeEventIDs.isEmpty || scenePhase != .active)
                        if !controller.activeEventIDs.isEmpty {
                            Text("Another game has a Live Activity. Stop it before starting this game.")
                                .font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    if presentation.showsUpdateNote {
                        Text("Updates while this game is open. After you leave, the reading can become stale.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    if let status = controller.status {
                        Text(status).font(.footnote).foregroundStyle(.secondary)
                            .accessibilityIdentifier("game.activity.status")
                    }
                }
            }
        }
        // Keep lifecycle delivery attached even when the control is hidden:
        // a terminal reading must still end an existing activity.
        .task(id: snapshot) {
            controller.reconcile()
            guard scenePhase == .active else { return }
            controller.beginViewing(eventID: snapshot.eventID)
            await controller.update(snapshot: snapshot)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                controller.beginViewing(eventID: snapshot.eventID)
                Task {
                    controller.reconcile()
                    await controller.update(snapshot: snapshot)
                }
            } else { controller.endViewing(eventID: snapshot.eventID) }
        }
        .onDisappear {
            controller.endViewing(eventID: snapshot.eventID)
        }
    }
}
/// Visibility is separate from lifecycle delivery: hiding chrome must not skip final updates.
nonisolated struct GameActivityControlPresentation {
    let isPhone: Bool
    let isEnabled: Bool
    let isTerminal: Bool
    let isActive: Bool

    var showsControl: Bool { isPhone && isEnabled && (!isTerminal || isActive) }
    var showsUpdateNote: Bool { showsControl && isActive && !isTerminal }
}
#endif
