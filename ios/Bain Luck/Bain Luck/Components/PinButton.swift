import SwiftUI

/// Never `.disabled`: at the pin limit the tap still reaches `togglePin`, which
/// says why nothing was pinned. A dimmed button that ignores taps is the
/// silent path #9495 removed.
struct PinButton: View {
    let type: String
    let id: Int
    var compact: Bool = false
    @EnvironmentObject var pinManager: PinManager

    private var pinned: Bool { pinManager.isPinned(type: type, id: id) }
    private var saving: Bool { pinManager.isSaving(type: type, id: id) }

    var body: some View {
        Button {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            pinManager.togglePin(type: type, id: id)
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
        .accessibilityLabel(saving ? "Saving pin" : (pinned ? "Unpin" : "Pin"))
    }
}
