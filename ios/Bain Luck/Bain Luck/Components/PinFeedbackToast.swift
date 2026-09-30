import SwiftUI

struct PinFeedbackToast: View {
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    /// Distance from the bottom safe area. On iPhone the floating tab bar sits
    /// inside that area, and at 22pt the toast was drawn over the tab labels
    /// (#9495 simulator LOOK on the game page). iPad's tab bar is at the top.
    static func bottomClearance(horizontalSizeClass: UserInterfaceSizeClass?) -> CGFloat {
        horizontalSizeClass == .regular ? 22 : 76
    }

    /// How long a settled outcome stays up. A pending save has no timer: its
    /// outcome replaces it. A warning is two lines and asks the reader to act,
    /// so it stays longer than a confirmation.
    static func displaySeconds(for feedback: PinActionFeedback) -> Double? {
        if feedback.isPending || feedback.managementType != nil { return nil }
        return feedback.isWarning ? 4.0 : 2.5
    }

    var body: some View {
        VStack {
            Spacer()
            if let feedback = pinManager.feedback {
                HStack(spacing: 8) {
                    if feedback.isPending {
                        ProgressView()
                            .controlSize(.small)
                            .tint(.white)
                    } else {
                        Image(systemName: feedback.systemImage)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(feedback.isWarning ? .orange : .white)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text(feedback.message)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.white)
                            .multilineTextAlignment(.leading)
                        if let type = feedback.managementType {
                            Button("Manage pins") { pinManager.presentManagement(type: type) }
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.white)
                                .accessibilityIdentifier("pinLimitManagePins")
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                // One opaque dark background for every outcome: a translucent
                // orange warning was unreadable over page content.
                .background(
                    RoundedRectangle(cornerRadius: 22)
                        .fill(Color.black.opacity(0.85))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 22)
                        .stroke(feedback.isWarning ? Color.orange.opacity(0.6) : Color.white.opacity(0.08), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.18), radius: 14, x: 0, y: 6)
                .padding(.horizontal, 20)
                .padding(.bottom, Self.bottomClearance(horizontalSizeClass: horizontalSizeClass))
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .allowsHitTesting(feedback.managementType != nil)
                .id(feedback.id)
                .task(id: feedback.id) {
                    guard let seconds = Self.displaySeconds(for: feedback) else { return }
                    try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                    await MainActor.run {
                        if pinManager.feedback?.id == feedback.id {
                            withAnimation(.easeOut(duration: 0.18)) {
                                pinManager.feedback = nil
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Spacer and clear layout have no hit surface; only the visible action
        // accepts taps. Presentation survives replacement/timeout of feedback.
        .sheet(item: $pinManager.managementPresentation) { request in
            PinManagementView(focusType: request.focusType).environmentObject(pinManager)
        }
        .animation(.spring(response: 0.24, dampingFraction: 0.88), value: pinManager.feedback?.id)
    }
}
