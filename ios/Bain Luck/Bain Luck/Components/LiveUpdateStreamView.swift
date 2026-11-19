import Combine
import SwiftUI

/// #10090 / #12938 — what a tap on the EKG opens: recent venue updates feeding
/// the headline, newest at the top, each with its venue on one line, the venue's
/// chance for the home team after it, and its receipt time on one line to the
/// second (`LiveUpdateStream`). Consecutive identical venue + probability rows
/// collapse into their newest receipt, and only whole rows draw (no mid-row
/// scroll clipping). "Details" opens the page's details popover.
struct LiveUpdateStreamView: View {
    let stream: LiveUpdateStream
    var homeTeam: String? = nil
    var onDetails: (() -> Void)? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var screen: LiveUpdateScreen?
    private let tick = Timer.publish(every: 0.04, on: .main, in: .common).autoconnect()

    private var maxVisibleRows: Int {
        if dynamicTypeSize.isAccessibilitySize {
            return 4
        }
        return dynamicTypeSize >= .xxLarge ? 7 : 8
    }

    var body: some View {
        let sourceRows = screen?.rows ?? LiveUpdateScreen(opening: stream.updates).rows
        let rows = LiveUpdateStream.displayRows(sourceRows, maxCount: maxVisibleRows)
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Updates feeding this number")
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                if let homeTeam {
                    Text("\(homeTeam) chance at each venue update")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if rows.isEmpty {
                Text("Waiting for the next update…")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("live-update-stream-empty")
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(rows) { update in
                        rowView(for: update)
                            .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                    }
                }
                .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: rows.first?.id)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("live-update-stream")
            }
            if let onDetails {
                Button("Details", action: onDetails)
                    .font(.footnote)
                    .padding(.top, 2)
                    .accessibilityIdentifier("live-update-stream-details")
            }
        }
        .padding(14)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear { screen = LiveUpdateScreen(opening: stream.updates) }
        .onChange(of: stream.updates.first?.id) { advance() }
        .onReceive(tick) { _ in if screen?.waiting == true { advance() } }
    }

    @ViewBuilder
    private func rowView(for update: LiveUpdateStream.Update) -> some View {
        let venue = LiveUpdateStream.venueName(update.source)
        let prob = LiveUpdateStream.probabilityText(update.p)
        let time = LiveUpdateStream.timeText(update.at)

        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(venue)
                    .font(.footnote.weight(.medium))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Spacer(minLength: 8)
                Text(prob)
                    .font(.footnote.monospacedDigit())
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Text(time)
                    .font(.footnote.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: 84, alignment: .trailing)
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(venue)
                        .font(.footnote.weight(.medium))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    Spacer(minLength: 6)
                    Text(prob)
                        .font(.footnote.monospacedDigit())
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                Text(time)
                    .font(.footnote.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func advance() {
        guard var next = screen else { return }
        next.advance(stream.updates, now: ProcessInfo.processInfo.systemUptime)
        if next != screen { screen = next }
    }
}
