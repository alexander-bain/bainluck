import Foundation

nonisolated struct PinAccountBinding: Hashable, Sendable {
    let userID: String?
    let authenticated: Bool
}

nonisolated enum PinLoadState: Equatable, Sendable {
    case local, loading, loaded, failed
}

nonisolated struct SavedPin: Identifiable, Hashable, Sendable {
    let type: String
    let value: Int
    var id: String { "\(type):\(value)" }
    var fallbackTitle: String { "Saved \(type == "event" ? "game" : "market")" }

    func displayTitle(for metadata: PinMetadata?) -> String {
        switch metadata {
        case .available(let title):
            let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty ? fallbackTitle : title
        case .unavailable:
            return "A saved \(type == "event" ? "game" : "market") that's no longer listed"
        default:
            return fallbackTitle
        }
    }

    func removeLabel(for metadata: PinMetadata?) -> String {
        "Remove \(displayTitle(for: metadata))"
    }
}

nonisolated struct PinManagementRequest: Identifiable {
    let id = UUID()
    var focusType: String? = nil
}

nonisolated enum PinMetadata: Equatable, Sendable {
    case available(title: String)
    case unavailable
    case failed
}
