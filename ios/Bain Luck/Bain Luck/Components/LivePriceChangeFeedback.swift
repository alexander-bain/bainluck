import SwiftUI

/// Presentation uses accepted, locally received activity, never a quote/publication clock.
nonisolated enum LivePriceFeedbackPresentation {
    static func shouldShow(previousSequence: Int?, sequence: Int,
                           valueChanged: Bool, isEnabled: Bool) -> Bool {
        guard let previousSequence else { return false }
        return isEnabled && valueChanged && sequence > previousSequence
    }

    static func receiptAge(receivedAt: Date, now: Date) -> String {
        let seconds = max(0, now.timeIntervalSince(receivedAt))
        if seconds < 1 { return "just now" }
        if seconds < 2 { return "1 second ago" }
        if seconds < 60 { return "\(Int(seconds)) seconds ago" }
        if seconds < 120 { return "1 minute ago" }
        if seconds < 3600 { return "\(Int(seconds / 60)) minutes ago" }
        if seconds < 7200 { return "1 hour ago" }
        if seconds < 86400 { return "\(Int(seconds / 3600)) hours ago" }
        if seconds < 172800 { return "1 day ago" }
        return "\(Int(seconds / 86400)) days ago"
    }
}

private struct PriceFeedbackTrigger: Equatable {
    let sequence: Int
    let enabled: Bool
    let reduceMotion: Bool
}

/// Attach only to the small printed price, never the containing chart or page.
extension View {
    func livePriceChangeFeedback(sequence: Int, valueChanged: Bool,
                                 color: Color = .accentColor,
                                 isEnabled: Bool = true) -> some View {
        modifier(LivePriceChangeFeedbackModifier(sequence: sequence,
            valueChanged: valueChanged, color: color, isEnabled: isEnabled))
    }
}

private struct LivePriceChangeFeedbackModifier: ViewModifier {
    let sequence: Int
    let valueChanged: Bool
    let color: Color
    let isEnabled: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        content
            // Replace digits immediately. Crossfading old/new glyphs can briefly
            // look like a third value; motion belongs to the highlight only.
            .background {
                LivePriceFeedbackFlash(sequence: sequence, valueChanged: valueChanged,
                    color: color, isEnabled: isEnabled, isEndpoint: false)
            }
    }
}

/// Position this independent leaf over the newest chart point. It cannot intercept scrubbing.
struct LivePriceEndpointPulse: View {
    let sequence: Int
    let valueChanged: Bool
    var color: Color = .accentColor
    var isEnabled: Bool = true

    var body: some View {
        LivePriceFeedbackFlash(sequence: sequence, valueChanged: valueChanged,
            color: color, isEnabled: isEnabled, isEndpoint: true)
            .frame(width: 14, height: 14)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

private struct LivePriceFeedbackFlash: View {
    let sequence: Int
    let valueChanged: Bool
    let color: Color
    let isEnabled: Bool
    let isEndpoint: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var previousSequence: Int?
    @State private var progress = 1.0

    private var trigger: PriceFeedbackTrigger {
        PriceFeedbackTrigger(sequence: sequence,
            enabled: isEnabled && scenePhase == .active, reduceMotion: reduceMotion)
    }

    var body: some View {
        Group {
            if isEndpoint {
                Circle().stroke(color, lineWidth: 1.5)
                    .scaleEffect(reduceMotion ? 1 : 1 + progress * 1.2)
                    .opacity((1 - progress) * 0.65)
            } else {
                RoundedRectangle(cornerRadius: 5)
                    .fill(color.opacity((1 - progress) * 0.16))
            }
        }
        .opacity(trigger.enabled ? 1 : 0)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .task(id: trigger) {
            let show = LivePriceFeedbackPresentation.shouldShow(
                previousSequence: previousSequence, sequence: sequence,
                valueChanged: valueChanged, isEnabled: trigger.enabled)
            previousSequence = sequence
            var reset = Transaction()
            reset.disablesAnimations = true
            withTransaction(reset) { progress = 1 }
            guard show else { return }
            // Reduce Motion keeps a brief static numeric highlight, with no ring or movement.
            if reduceMotion && isEndpoint { return }
            withTransaction(reset) { progress = 0 }
            if !reduceMotion {
                // Let the leaf's initial flash render before its one-shot fade;
                // otherwise SwiftUI can coalesce both writes into the invisible end state.
                do { try await Task.sleep(for: .milliseconds(20)) }
                catch { return }
                guard !Task.isCancelled else { return }
                withAnimation(.easeOut(duration: 0.6)) { progress = 1 }
            }
            do { try await Task.sleep(for: .milliseconds(600)) }
            catch { return }
            guard !Task.isCancelled else { return }
            withTransaction(reset) { progress = 1 }
        }
    }
}

/// Caller supplies a named-team caption and mounts this reserved slot only while live.
struct LivePriceMovementCaption: View {
    let sequence: Int
    let text: String?
    var color: Color = .accentColor
    var isEnabled: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @ScaledMetric(relativeTo: .caption2) private var slotHeight: CGFloat = 32
    @State private var previousSequence: Int?
    @State private var shownText: String?

    private var trigger: PriceFeedbackTrigger {
        PriceFeedbackTrigger(sequence: sequence,
            enabled: isEnabled && scenePhase == .active, reduceMotion: reduceMotion)
    }

    var body: some View {
        Text(shownText ?? " ")
            .font(.caption2)
            .foregroundStyle(color)
            .lineLimit(2)
            .frame(height: slotHeight, alignment: .topLeading)
            .opacity(trigger.enabled && shownText != nil ? 1 : 0)
            .accessibilityHidden(!trigger.enabled || shownText == nil)
            .allowsHitTesting(false)
            .task(id: trigger) {
                let show = LivePriceFeedbackPresentation.shouldShow(
                    previousSequence: previousSequence, sequence: sequence,
                    valueChanged: text != nil, isEnabled: trigger.enabled)
                previousSequence = sequence
                shownText = nil
                guard show else { return }
                shownText = text
                do { try await Task.sleep(for: .seconds(2)) }
                catch { return }
                guard !Task.isCancelled else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                    shownText = nil
                }
            }
    }
}

/// Mount only inside the open reveal/popover. The age clock lives here, not on the page.
struct FreshnessRevealView: View {
    let status: LiveUpdateStatus
    let lastReceivedAt: Date?
    var confidenceTier: String? = nil
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if status != .hidden {
                Text(status.title).font(.headline)
            }
            if let lastReceivedAt {
                if scenePhase == .active {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        receipt(lastReceivedAt, now: context.date)
                    }
                } else {
                    receipt(lastReceivedAt, now: .now)
                }
                Text("Received on this device at \(lastReceivedAt.formatted(date: .abbreviated, time: .standard)).")
                    .foregroundStyle(.secondary)
            } else {
                Text("No newer price update received since opening this page.")
            }
            if let tier = Confidence.normalize(confidenceTier) {
                Text(tier.label)
                Text(Confidence.tooltip)
                    .foregroundStyle(.secondary)
            }
        }
        .font(.callout)
        .fixedSize(horizontal: false, vertical: true)
        .padding()
    }

    private func receipt(_ receivedAt: Date, now: Date) -> some View {
        Text("Last price update received \(LivePriceFeedbackPresentation.receiptAge(receivedAt: receivedAt, now: now)).")
    }
}
