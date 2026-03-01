import SwiftUI

/// Live (red pulse), Scheduled countdown, Final (gray).
struct StatusBadge: View {
    let status: String?
    var commenceTime: String? = nil

    var body: some View {
        switch status {
        case "live":
            HStack(spacing: 4) {
                Circle()
                    .fill(.red)
                    .frame(width: 6, height: 6)
                    .modifier(PulseAnimation())
                Text("LIVE")
                    .font(.caption2)
                    .fontWeight(.bold)
                    .foregroundStyle(.red)
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.red.opacity(0.1))
            .clipShape(Capsule())
        case "completed", "closed":
            Text("FINAL")
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.cardBackgroundDark)
                .clipShape(Capsule())
        case "scheduled":
            if let ct = commenceTime, let date = ct.asDate, let countdown = formatCountdown(from: date) {
                HStack(spacing: 3) {
                    Image(systemName: "clock")
                        .font(.system(size: 8))
                    Text("In \(countdown)")
                        .font(.caption2)
                        .fontWeight(.medium)
                }
                .foregroundStyle(.blue)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(.blue.opacity(0.1))
                .clipShape(Capsule())
            } else {
                EmptyView()
            }
        default:
            EmptyView()
        }
    }
}

private struct PulseAnimation: ViewModifier {
    @State private var animating = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(animating ? 1.3 : 1.0)
            .opacity(animating ? 0.6 : 1.0)
            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: animating)
            .onAppear { animating = true }
    }
}
