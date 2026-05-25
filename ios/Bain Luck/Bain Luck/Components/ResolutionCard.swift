import SwiftUI

struct NativeResolutionCard: View {
    let resolution: Resolution

    var body: some View {
        HStack(spacing: 12) {
            // Result indicator
            ZStack {
                Circle()
                    .fill(resolution.correct ? Color.green.opacity(0.12) : Color.red.opacity(0.12))
                    .frame(width: 44, height: 44)
                Image(systemName: resolution.correct ? "checkmark" : "xmark")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(resolution.correct ? .green : .red)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text("RESOLVED")
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(0.8)
                    .foregroundStyle(.purple)

                Text(resolution.marketName)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                Text(resolution.correct ? "You got it right!" : "Better luck next time")
                    .font(.caption)
                    .foregroundStyle(resolution.correct ? .green : .secondary)
            }

            Spacer(minLength: 0)
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(resolution.correct ? Color.green.opacity(0.3) : Color.barTrack.opacity(0.55), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
    }
}
