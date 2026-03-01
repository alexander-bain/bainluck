import SwiftUI

struct PinButton: View {
    let type: String
    let id: Int
    var compact: Bool = false
    @EnvironmentObject var pinManager: PinManager

    private var pinned: Bool { pinManager.isPinned(type: type, id: id) }
    private var disabled: Bool { !pinned && !pinManager.canPin(type: type) }

    var body: some View {
        Button {
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            pinManager.togglePin(type: type, id: id)
        } label: {
            Image(systemName: pinned ? "bookmark.fill" : "bookmark")
                .font(.system(size: compact ? 12 : 14))
                .foregroundStyle(pinned ? .orange : .secondary)
                .frame(width: compact ? 28 : 44, height: compact ? 28 : 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(disabled ? 0.3 : 1.0)
        .disabled(disabled)
        .accessibilityLabel(pinned ? "Unpin" : "Pin")
    }
}
