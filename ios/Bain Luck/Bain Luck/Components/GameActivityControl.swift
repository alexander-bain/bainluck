#if os(iOS) && canImport(ActivityKit)
import SwiftUI

/// Explicit foreground-only activity controls; never a background-live promise.
struct GameActivityControl: View {
    let snapshot: GameActivitySnapshot
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject private var controller = GameActivityController.shared

    var body: some View {
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
                    .disabled(controller.isBusy || !controller.isEnabled || snapshot.isTerminal
                              || !controller.activeEventIDs.isEmpty || scenePhase != .active)
                if !controller.activeEventIDs.isEmpty {
                    Text("Another game has a Live Activity. Stop it before starting this game.")
                        .font(.footnote).foregroundStyle(.secondary)
                } else if !controller.isEnabled {
                    Text("Live Activities are unavailable or disabled in Settings.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Text("Updates while this app is open. After you leave, the reading can become stale.")
                .font(.footnote).foregroundStyle(.secondary)
            if let status = controller.status {
                Text(status).font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("game.activity.status")
            }
        }
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
#endif
