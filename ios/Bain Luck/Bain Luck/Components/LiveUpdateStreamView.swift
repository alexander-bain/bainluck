import Combine
import SwiftUI

/// #10090 (Alex 2026-11-01) — what a tap on the EKG opens: every venue update
/// feeding the headline, newest at the top, each with its source, the venue's
/// chance for the home team after it, and its receipt time to the hundredth of
/// a second (`LiveUpdateStream`). Rows stream in at the venues' own pace
/// (`LiveUpdateScreen`), sliding in from the top; under Reduce Motion they
/// appear without the slide. "Details" opens the page's details popover.
struct LiveUpdateStreamView: View {
    let stream: LiveUpdateStream
    var homeTeam: String? = nil
    var onDetails: (() -> Void)? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var screen: LiveUpdateScreen?
    private let tick = Timer.publish(every: 0.04, on: .main, in: .common).autoconnect()

    var body: some View {
        let rows = screen?.rows ?? []
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Updates feeding this number")
                    .font(.subheadline.weight(.semibold))
                if let homeTeam {
                    Text("\(homeTeam) chance at each venue update")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if rows.isEmpty {
                Text("Waiting for the next update…")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("live-update-stream-empty")
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(rows) { update in
                            HStack(spacing: 12) {
                                Text(LiveUpdateStream.venueName(update.source))
                                    .font(.footnote.weight(.medium))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                Text(LiveUpdateStream.probabilityText(update.p))
                                    .font(.footnote.monospacedDigit())
                                Text(LiveUpdateStream.timeText(update.at))
                                    .font(.footnote.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                        }
                    }
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: rows.first?.id)
                }
                .frame(maxHeight: 280)
                .accessibilityIdentifier("live-update-stream")
            }
            if let onDetails {
                Button("Details", action: onDetails)
                    .font(.footnote)
                    .accessibilityIdentifier("live-update-stream-details")
            }
        }
        .padding(14)
        .onAppear { screen = LiveUpdateScreen(opening: stream.updates) }
        .onChange(of: stream.updates.first?.id) { advance() }
        .onReceive(tick) { _ in if screen?.waiting == true { advance() } }
    }

    private func advance() {
        guard var next = screen else { return }
        next.advance(stream.updates, now: ProcessInfo.processInfo.systemUptime)
        if next != screen { screen = next }
    }
}
