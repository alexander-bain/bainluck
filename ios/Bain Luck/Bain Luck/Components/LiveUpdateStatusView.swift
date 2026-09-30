import SwiftUI

/// Delivery evidence, not a promise about quote age or connection speed.
nonisolated enum LiveUpdateStatus: Equatable {
    case hidden, awaitingUpdate, live, autoRefresh, interrupted

    static func decide(status: String?, delivering: Bool, acceptedUpdate: Bool,
                       refreshFailed: Bool) -> Self {
        guard EventPriceStreaming.isEligible(status) else { return .hidden }
        if delivering && acceptedUpdate { return .live }
        if refreshFailed { return .interrupted }
        return delivering ? .awaitingUpdate : .autoRefresh
    }

    var title: String {
        switch self {
        case .hidden: return ""
        case .awaitingUpdate: return "Waiting for update"
        case .live: return "Live updates"
        case .autoRefresh: return "Auto-refresh"
        case .interrupted: return "Update interrupted"
        }
    }

    var accessibilityText: String {
        switch self {
        case .hidden: return ""
        case .awaitingUpdate: return "Connected. Waiting for a live price update."
        case .live: return "Live updates. A live price update has reached this page."
        case .autoRefresh: return "Live updates unavailable. Checking automatically."
        case .interrupted: return "Update interrupted. The last refresh failed."
        }
    }
}

/// Shared by the page and fullscreen chart. No timer, animation or refresh action.
struct LiveUpdateStatusView: View {
    let status: LiveUpdateStatus

    var body: some View {
        if status != .hidden {
            HStack(spacing: 4) {
                if status == .live {
                    Circle().fill(.green).frame(width: 5, height: 5)
                }
                Text(status.title)
                    .font(.caption2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(.secondary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(status.accessibilityText)
            .accessibilityIdentifier("live-update-status")
        }
    }
}
