import Foundation
import WidgetKit

/// Pure deep-link tagger for `#13261` row 13 (widget opens).
/// Runs inside `BainLuckWidget` without importing Firebase or any analytics SDK.
enum WidgetLinkTagging13261 {
    static let allowedKinds: Set<String> = [
        "live_games_small",
        "live_games_medium",
        "live_games_large",
        "saved_small",
        "saved_medium",
        "saved_lock_rect",
        "saved_lock_circle",
        "saved_item",
    ]

    static func savedKind(for family: WidgetFamily) -> String {
        switch family {
        case .systemSmall: return "saved_small"
        case .systemMedium: return "saved_medium"
        #if os(iOS)
        case .accessoryRectangular: return "saved_lock_rect"
        case .accessoryCircular: return "saved_lock_circle"
        #endif
        default: return "saved_item"
        }
    }

    static func tagged(_ url: URL?, kind: String) -> URL? {
        guard let url, allowedKinds.contains(kind),
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        var items = (components.queryItems ?? []).filter { $0.name != "source" && $0.name != "widget_kind" }
        items.append(URLQueryItem(name: "source", value: "widget"))
        items.append(URLQueryItem(name: "widget_kind", value: kind))
        components.queryItems = items
        return components.url ?? url
    }

    static func tagged(_ url: URL, kind: String) -> URL {
        tagged(Optional(url), kind: kind) ?? url
    }
}
