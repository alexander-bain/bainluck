import SwiftUI

/// Collapses N resolution notes into a single digest card (#902 item 8) so the
/// feed top isn't a stack of "RESOLVED" cards. Taps through to prediction stats.
struct NativeResolutionDigestCard: View {
    let total: Int
    let correct: Int

    private var headline: String {
        let noun = total == 1 ? "prediction" : "predictions"
        return "\(total) \(noun) resolved"
    }

    private var subline: String {
        "\(correct) right"
    }

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color.purple.opacity(0.12))
                    .frame(width: 44, height: 44)
                Image(systemName: "checklist")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(.purple)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text("RESOLVED")
                    .font(.system(size: 9, weight: .heavy))
                    .tracking(0.8)
                    .foregroundStyle(.purple)

                Text(headline)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)

                Text(subline)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.barTrack.opacity(0.55), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
    }
}

/// Honest end-of-feed card (#902 item 9) shown once pagination is exhausted.
/// Cadence ("every couple of hours") is derived from the documented ingestion
/// poll cadences (Polymarket every 1h, Kalshi every 2h) — see CLAUDE.md.
struct NativeFeedEndCard: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 28))
                .foregroundStyle(.green)
            Text("You're all caught up")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.primary)
            Text("New markets surface roughly every couple of hours — pull to refresh.")
                .font(.caption)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28)
        .padding(.horizontal, 16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.barTrack.opacity(0.45), lineWidth: 1)
        )
    }
}
