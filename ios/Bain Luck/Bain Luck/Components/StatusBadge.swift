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

    /// The arms are an if/else chain rather than a `switch` on purpose: the
    /// settled pair is `EventState.isFinished`, not two string literals this
    /// file gets to spell for itself. #4002 was one private copy of that
    /// vocabulary going stale; a badge is the last place a second copy belongs.
    @ViewBuilder
    var body: some View {
        if status == "live" {
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
        } else if EventState.isFinished(status) {
            Text("FINAL")
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.cardBackgroundDark)
                .clipShape(Capsule())
        } else if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime?.asDate) {
            // 🔴 #4021 — THE CLOCK IS PART OF THE TEST, and it has to be tested
            // HERE rather than left to callers. Three of this component's five
            // call sites (`SearchView` ×2, `TeamDetailView`) hand it a raw
            // `event.status`, so a suspended arm that trusted the status alone
            // would have put "No result reported" on a search row and a team
            // schedule row for event 416569 — Ohio State @ Texas, four days
            // BEFORE kick-off. Those callers now pass `commenceTime` too.
            //
            // A caller that passes none still gets the badge, matching
            // `EventState.hasStarted`'s documented default; a caller that passes
            // a FUTURE one falls through to `EmptyView`, which is exactly what
            // master did for it, so no surface loses a badge it had.
            //
            // #4002 — the state that had no badge at all. It cannot borrow
            // FINAL's grey silence: FINAL is read against a score, and this one
            // is read against a hero that may have nothing else on it. The
            // wording is `EventState.suspendedLabel` and NOT the bare word
            // "Suspended" for the reason stated where it is defined — the same
            // status covers a rain delay and a source going dark, and only one
            // of those is a stoppage anybody reported.
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.circle")
                    .font(.system(size: 8))
                Text(EventState.suspendedLabel)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.orange)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.orange.opacity(0.1))
            .clipShape(Capsule())
        } else if status == "scheduled" {
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
        } else {
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
