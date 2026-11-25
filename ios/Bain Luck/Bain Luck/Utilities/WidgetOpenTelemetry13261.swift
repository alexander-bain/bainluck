import Foundation

/// Pure parser for `#13261` rows 11–13 telemetry on the main app (`AnalyticsService`),
/// collapsing any unexpected or arbitrary parameter strings to closed safe defaults.
nonisolated struct WidgetOpenDescriptor13261: Equatable, Sendable {
    let widgetKind: String
    let destinationType: String
}

nonisolated enum WidgetAndAlertTelemetry13261 {
    static let allowedWidgetKinds: Set<String> = [
        "live_games_small",
        "live_games_medium",
        "live_games_large",
        "saved_small",
        "saved_medium",
        "saved_lock_rect",
        "saved_lock_circle",
        "saved_item",
    ]

    static func normalizedWidgetKind(_ raw: String?) -> String {
        guard let raw else { return "unknown" }
        let cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowedWidgetKinds.contains(cleaned) ? cleaned : "unknown"
    }

    /// Returns a descriptor only when the opened URL came from a Bain Luck widget
    /// (`?source=widget`). Arbitrary widget_kind values collapse to `"unknown"`.
    static func parseWidgetOpen(url: URL, destinationType: String) -> WidgetOpenDescriptor13261? {
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        guard let source = items.first(where: { $0.name == "source" })?.value?
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              source == "widget" else {
            return nil
        }
        let rawKind = items.first(where: { $0.name == "widget_kind" })?.value
        return WidgetOpenDescriptor13261(
            widgetKind: normalizedWidgetKind(rawKind),
            destinationType: destinationType
        )
    }

    static func destinationType(for pathComponents: [String]) -> String {
        guard let head = pathComponents.first else { return "other" }
        switch head {
        case "events":
            return pathComponents.count >= 2 && Int(pathComponents[1]) != nil ? "event" : "sports"
        case "futures":
            return "futures"
        case "my-stuff":
            return "my_stuff"
        case "search":
            return "search"
        case "containers", "collections":
            return "collection"
        case "tournaments":
            return "tournament"
        default:
            return "other"
        }
    }
}
