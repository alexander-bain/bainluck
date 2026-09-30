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
    @State private var showLimitAlert = false
    @State private var showPinManagement = false
    @State private var limitMessage = ""

    private var pinned: Bool { pinManager.isPinned(type: type, id: id) }
    private var saving: Bool { pinManager.isSaving(type: type, id: id) }

    var body: some View {
        Button {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            let previousFeedbackID = pinManager.feedback?.id
            pinManager.togglePin(type: type, id: id)
            // A root overlay may sit below a presented detail sheet. Its pin
            // button owns a local limit alert and a sheet above that detail.
            if isPresented, let feedback = pinManager.feedback,
               feedback.id != previousFeedbackID, feedback.managementType == type {
                limitMessage = feedback.message
                showLimitAlert = true
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
        .alert("Pin limit reached", isPresented: $showLimitAlert) {
            Button("Manage pins") { showPinManagement = true }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text(limitMessage)
        }
        .sheet(isPresented: $showPinManagement) {
            PinManagementView(focusType: type).environmentObject(pinManager)
        }
        .onChange(of: pinManager.identityGeneration) { _, _ in
            showLimitAlert = false
            showPinManagement = false
        }
        .accessibilityLabel(saving ? "Saving pin" : (pinned ? "Unpin" : "Pin"))
    }
}
