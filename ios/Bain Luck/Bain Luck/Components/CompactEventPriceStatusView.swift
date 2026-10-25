import SwiftUI

/// #8320 (v24) — the hero's one delivery cue, collapsed to a single line.
///
/// Build 32 (Martin Tiffon–Lokoli, `chart-9655-after.md`): a local receipt time
/// with seconds in the centre of the hero was "embarrassing". The collapsed cue
/// says only the connection state; the exact device receipt time lives in the
/// tap disclosure (`FreshnessRevealView`) and nowhere in the hero.
///
/// Pure presentation of an existing `LiveUpdateStatus`: no state decision, no
/// lifecycle inference (a scheduled game that is waiting still says so — that
/// is the status owner's call, not this renderer's), no price arithmetic.
nonisolated struct CompactEventPriceStatus: Equatable {
    let status: LiveUpdateStatus
    var isDisclosure: Bool = false
    /// #11285 (Alex, build 65) — the adopted headline's top-row control says
    /// every delivery state in its details, never beside the icon: "Waiting
    /// for updates" there squeezed the headline. An interruption keeps its
    /// warning glyph and tint, so a failure is still seen without the words;
    /// the headline's own phase line already reads "last recorded" (#9483).
    var statusInDetails: Bool = false

    var isVisible: Bool { isDisclosure || status != .hidden }

    /// Routine status lives in details; uncertainty remains beside the price,
    /// except where the whole status lives in details (#11285).
    var showsTitle: Bool {
        if isDisclosure && statusInDetails { return false }
        return !isDisclosure || (status != .live && status != .hidden)
    }

    var showsTrailingInfo: Bool { isDisclosure && showsTitle }

    var title: String { status.title }

    /// Only proven delivery is green; every other state is neutral or a warning.
    var glyph: String {
        if isDisclosure && statusInDetails && status == .interrupted { return "exclamationmark.triangle.fill" }
        if isDisclosure && !showsTitle { return "info.circle" }
        switch status {
        case .hidden: return ""
        case .live: return "circle.fill"
        case .awaitingUpdate: return "circle.dotted"
        case .autoRefresh: return "arrow.triangle.2.circlepath"
        case .interrupted: return "exclamationmark.triangle.fill"
        }
    }

    /// The acknowledgement glyph. Says "received", never "moved".
    static let receiptGlyph = "checkmark.circle.fill"

    /// A receipt can be acknowledged only while the reader can see it and the
    /// status is not claiming a failure. Same gate as `VisibleLivePriceStatusView`.
    static func acknowledgesReceipts(status: LiveUpdateStatus, sceneActive: Bool) -> Bool {
        sceneActive && status != .hidden && status != .interrupted
    }
}

/// One line beside the probabilities. No receipt time, age timer, chart state or
/// periodic pulse; no button — the holder's disclosure button wraps it.
struct CompactEventPriceStatusView: View {
    let status: LiveUpdateStatus
    let sequence: Int
    let receivedAt: Date?
    /// The owning button opens the existing details popover. Default preserves
    /// every other caller's delivery-status presentation.
    var isDisclosure: Bool = false
    /// #11285 — every state behind the control (`CompactEventPriceStatus`).
    var statusInDetails: Bool = false
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var cue = LivePriceReceiptCue()
    @State private var acknowledged = false

    private struct Trigger: Equatable {
        let sequence: Int
        let status: LiveUpdateStatus
        let active: Bool
        let reduceMotion: Bool
    }

    private var presentation: CompactEventPriceStatus { CompactEventPriceStatus(status: status, isDisclosure: isDisclosure, statusInDetails: statusInDetails) }

    private var tint: Color {
        if acknowledged || (!isDisclosure && status == .live) { return DS.emerald }
        return status == .interrupted ? DS.amber : DS.textSecondary
    }

    var body: some View {
        if presentation.isVisible {
            HStack(spacing: 4) {
                // #9483 — one glyph slot in the disclosure: a labelled state
                // carries only the trailing info mark (two glyphs wrapped
                // "Waiting for update" inside the hero's 150pt slot), and the
                // receipt checkmark takes that same slot while acknowledged.
                if !presentation.showsTrailingInfo {
                    Image(systemName: acknowledged ? CompactEventPriceStatus.receiptGlyph : presentation.glyph)
                        .imageScale(.small)
                        .accessibilityHidden(true)
                }
                if presentation.showsTitle {
                    Text(presentation.title)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if presentation.showsTrailingInfo {
                    Image(systemName: acknowledged ? CompactEventPriceStatus.receiptGlyph : "info.circle")
                        .imageScale(.small)
                        .accessibilityHidden(true)
                }
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(tint)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(DS.emerald.opacity(acknowledged ? 0.14 : 0), in: Capsule())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(LivePriceReceiptCue.accessibilityText(status: status, receivedAt: receivedAt))
            .accessibilityIdentifier("compact-event-price-status")
            .task(id: Trigger(sequence: sequence, status: status,
                              active: scenePhase == .active, reduceMotion: reduceMotion)) {
                var reset = Transaction()
                reset.disablesAnimations = true
                withTransaction(reset) { acknowledged = false }
                let show = cue.consume(sequence: sequence, receivedAt: receivedAt,
                    enabled: CompactEventPriceStatus.acknowledgesReceipts(status: status,
                        sceneActive: scenePhase == .active))
                guard show else { return }
                // A static glyph/tint swap reads with Reduce Motion too; only the
                // fade back is optional. Finite, once per accepted receipt.
                withTransaction(reset) { acknowledged = true }
                do { try await Task.sleep(for: .milliseconds(1200)) }
                catch { return }
                guard !Task.isCancelled else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { acknowledged = false }
            }
        }
    }
}
