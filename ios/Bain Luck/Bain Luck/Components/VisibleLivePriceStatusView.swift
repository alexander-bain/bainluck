import SwiftUI

/// A receipt cue is independent of numeric movement. The producer of `sequence`
/// already requires a newer adopted price revision, even if its printed % is unchanged.
nonisolated struct LivePriceReceiptCue: Equatable {
    private(set) var previousSequence: Int?

    mutating func consume(sequence: Int, receivedAt: Date?, enabled: Bool) -> Bool {
        defer { previousSequence = max(previousSequence ?? sequence, sequence) }
        guard enabled, receivedAt != nil, let previousSequence else { return false }
        return sequence > previousSequence
    }

    static func receiptText(_ receivedAt: Date?) -> String {
        guard let receivedAt else { return "No live update yet" }
        return "Received \(receivedAt.formatted(date: .omitted, time: .standard))"
    }

    static func accessibilityText(status: LiveUpdateStatus, receivedAt: Date?) -> String {
        let receipt = receivedAt.map {
            "Last price update received on this device at \($0.formatted(date: .abbreviated, time: .standard))."
        } ?? "No live update received on this page yet."
        return "\(status.accessibilityText) \(receipt)"
    }
}

/// Keep this leaf next to the probabilities. No age timer, chart state or periodic pulse.
struct VisibleLivePriceStatusView: View {
    let status: LiveUpdateStatus
    let sequence: Int
    let receivedAt: Date?
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var cue = LivePriceReceiptCue()
    @State private var highlighted = false

    private struct Trigger: Equatable {
        let sequence: Int
        let status: LiveUpdateStatus
        let active: Bool
        let reduceMotion: Bool
    }

    private var enabled: Bool {
        scenePhase == .active && status != .hidden && status != .interrupted
    }

    var body: some View {
        if status != .hidden {
            VStack(spacing: 3) {
                Text(status.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(status == .live ? DS.emerald : DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 4) {
                    Image(systemName: highlighted ? "checkmark.circle.fill" : "arrow.down.circle")
                    Text(LivePriceReceiptCue.receiptText(receivedAt))
                        .monospacedDigit()
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.caption2)
                .foregroundStyle(highlighted ? DS.emerald : DS.textSecondary)
                .padding(.horizontal, 5)
                .padding(.vertical, 3)
                .background(DS.emerald.opacity(highlighted ? 0.14 : 0), in: RoundedRectangle(cornerRadius: 5))
            }
            .multilineTextAlignment(.center)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(LivePriceReceiptCue.accessibilityText(status: status, receivedAt: receivedAt))
            .accessibilityIdentifier("visible-live-price-status")
            .task(id: Trigger(sequence: sequence, status: status,
                              active: scenePhase == .active, reduceMotion: reduceMotion)) {
                var reset = Transaction()
                reset.disablesAnimations = true
                withTransaction(reset) { highlighted = false }
                let show = cue.consume(sequence: sequence, receivedAt: receivedAt, enabled: enabled)
                guard show else { return }
                // Static checkmark/color also works with Reduce Motion. A finite
                // fade is optional; no fabricated price transition or looping animation.
                withTransaction(reset) { highlighted = true }
                do { try await Task.sleep(for: .milliseconds(1200)) }
                catch { return }
                guard !Task.isCancelled else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { highlighted = false }
            }
        }
    }
}
