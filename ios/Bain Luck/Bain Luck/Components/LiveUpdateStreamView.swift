import SwiftUI

/// #10090 (Alex 2026-11-01) — what a tap on the EKG opens: every venue update
/// feeding the headline, newest at the top, each with its source and receipt
/// time to the hundredth of a second (`LiveUpdateStream`). New rows slide in
/// from the top. Under Reduce Motion they appear without the slide. "Details"
/// opens the page's details popover (connection, confidence, forecast).
struct LiveUpdateStreamView: View {
    let stream: LiveUpdateStream
    var onDetails: (() -> Void)? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Updates feeding this number")
                .font(.subheadline.weight(.semibold))
            if stream.updates.isEmpty {
                Text("Waiting for the next update…")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("live-update-stream-empty")
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(stream.updates) { update in
                            HStack {
                                Text(LiveUpdateStream.venueName(update.source))
                                    .font(.footnote.weight(.medium))
                                Spacer(minLength: 12)
                                Text(LiveUpdateStream.timeText(update.at))
                                    .font(.footnote.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                        }
                    }
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: stream.updates.first?.id)
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
    }
}
