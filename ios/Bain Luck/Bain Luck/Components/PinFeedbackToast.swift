import SwiftUI

struct PinFeedbackToast: View {
    @EnvironmentObject private var pinManager: PinManager

    var body: some View {
        VStack {
            Spacer()
            if let feedback = pinManager.feedback {
                HStack(spacing: 8) {
                    Image(systemName: feedback.systemImage)
                        .font(.subheadline.weight(.semibold))
                    Text(feedback.message)
                        .font(.subheadline.weight(.semibold))
                }
                .foregroundStyle(feedback.isWarning ? .orange : .white)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    Capsule()
                        .fill(feedback.isWarning ? Color.orange.opacity(0.14) : Color.black.opacity(0.78))
                )
                .overlay(
                    Capsule()
                        .stroke(feedback.isWarning ? Color.orange.opacity(0.25) : Color.white.opacity(0.08), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.18), radius: 14, x: 0, y: 6)
                .padding(.bottom, 22)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .id(feedback.id)
                .task(id: feedback.id) {
                    try? await Task.sleep(nanoseconds: 1_800_000_000)
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
        .allowsHitTesting(false)
        .animation(.spring(response: 0.24, dampingFraction: 0.88), value: pinManager.feedback?.id)
    }
}
