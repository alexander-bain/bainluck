import SwiftUI

struct NativeResolutionCard: View {
    let resolution: Resolution

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text("📋")
                Text("MARKET RESOLVED")
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1)
                    .foregroundStyle(.purple)
                Spacer()
            }

            Text(resolution.marketName)
                .font(.subheadline.weight(.bold))
                .lineLimit(2)

            Text(resolution.correct ? "✓ You got it right!" : "✗ Better luck next time")
                .font(.caption.weight(.bold))
                .foregroundStyle(resolution.correct ? .green : .red)
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background((resolution.correct ? Color.green : Color.red).opacity(0.1))
                .clipShape(Capsule())

            Text("You guessed \(resolution.guess) than \(resolution.threshold)% — final: \(resolution.actual)%")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.purple.opacity(0.3), lineWidth: 2))
    }
}
