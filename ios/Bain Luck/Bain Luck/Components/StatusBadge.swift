import SwiftUI

/// Live (red pulse with optional game clock), Scheduled countdown, Final (gray).
struct StatusBadge: View {
    let status: String?
    var commenceTime: String? = nil
    /// ESPN game clock, e.g., "5:42"
    var gameClock: String? = nil
    /// RAW ESPN period. The comment here used to claim `"Q3"` / `"3rd Period"`,
    /// and that is not what arrives: the real value is `"5:11 - 1st Quarter"`,
    /// with the clock on the FRONT (#3273). Both call sites pass
    /// `event.espn?.period` straight through.
    var period: String? = nil

    /// Formatted live text: "Q1 5:11", "Bottom 7th", or "LIVE".
    ///
    /// #3273 — this read **"5:11 - 1st Quarter 5:11"** on the live Michigan game
    /// (photographed 2026-09-05), on the event hero AND on every sports feed
    /// card, because the raw period was joined to the clock it already contains.
    /// `PeriodLabel.liveBadgeLabel` shortens it while keeping baseball's
    /// half-inning, which is why "Bottom 7th" below is still whole.
    private var liveText: String {
        let label = period.map(PeriodLabel.liveBadgeLabel)
        var parts = [label, gameClock].compactMap { $0 }.filter { !$0.isEmpty }
        // Baseball has no game clock — "0:00" is meaningless
        if let clock = gameClock, clock == "0:00" || clock == "0" {
            parts = [label].compactMap { $0 }.filter { !$0.isEmpty }
        }
        return parts.isEmpty ? "LIVE" : parts.joined(separator: " ")
    }

    var body: some View {
        switch status {
        case "live":
            HStack(spacing: 4) {
                Circle()
                    .fill(.red)
                    .frame(width: 6, height: 6)
                    .modifier(PulseAnimation())
                Text(liveText)
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
            if let commence = commenceTime, let date = commence.asDate, let countdown = formatCountdown(from: date) {
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
