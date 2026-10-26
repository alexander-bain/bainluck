import SwiftUI

/// Never `.disabled`: at the pin limit the tap still reaches `togglePin`, which
/// says why nothing was pinned. A dimmed button that ignores taps is the
/// silent path #9495 removed.
struct PinButton: View {
    let type: String
    let id: Int
    var compact: Bool = false
    @EnvironmentObject var pinManager: PinManager
    @Environment(\.isPresented) private var isPresented
    @State private var showManagementAlert = false
    @State private var showPinManagement = false
    @State private var managementMessage = ""
    @State private var managementAlertTitle = "Manage pins"

    private var pinned: Bool { pinManager.isPinned(type: type, id: id) }
    private var saving: Bool { pinManager.isSaving(type: type, id: id) }

    var body: some View {
        Button {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            let previousFeedbackID = pinManager.feedback?.id
            let wasPinned = pinned
            pinManager.togglePin(type: type, id: id)
            // #10876 — a pin that took is the action its tip teaches.
            if !wasPinned, pinned { ContextualTips10876.pinLearned() }
            // A root overlay may sit below a presented detail sheet. Its pin
            // button owns a local limit alert and a sheet above that detail.
            if isPresented, let feedback = pinManager.feedback,
               feedback.id != previousFeedbackID, feedback.managementType == type {
                managementMessage = feedback.message
                managementAlertTitle = feedback.managementAlertTitle
                showManagementAlert = true
                pinManager.feedback = nil
            }
        } label: {
            Group {
                if saving {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Image(systemName: pinned ? "bookmark.fill" : "bookmark")
                        .font(.system(size: compact ? 12 : 14))
                        .foregroundStyle(pinned ? .orange : .secondary)
                }
            }
            .frame(width: compact ? 28 : 44, height: compact ? 28 : 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .alert(managementAlertTitle, isPresented: $showManagementAlert) {
            Button("Manage pins") { showPinManagement = true }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text(managementMessage)
        }
        .sheet(isPresented: $showPinManagement) {
            PinManagementView(focusType: type).environmentObject(pinManager)
        }
        .onChange(of: pinManager.identityGeneration) { _, _ in
            showManagementAlert = false
            showPinManagement = false
        }
        .accessibilityLabel(saving ? "Saving pin" : (pinned ? "Unpin" : "Pin"))
        // #10876 — the pin tip, on detail-page bookmarks only. Tips/ decides
        // it, so this button never reads the pin limit (#9495).
        .pinTip10876(isDetailAnchor: !compact, pinManager: pinManager, type: type, id: id,
                     localPinUIShowing: showManagementAlert || showPinManagement)
    }
}
