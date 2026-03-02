import Combine
import Foundation
import SwiftUI

/// Tab identifiers for programmatic tab switching.
enum AppTab: Int, Hashable {
    case feed = 0
    case search = 1
    case myStuff = 2
}

/// Coordinates deep link and universal link URL handling with tab navigation.
@MainActor
final class NavigationCoordinator: ObservableObject {
    @Published var selectedTab: AppTab = .feed
    @Published var pendingRoute: Route?
    @Published var pendingSearchQuery: String?
    @Published var liveGameCount: Int = 0

    /// Parse a URL and navigate to the appropriate destination.
    /// Returns `true` if the URL was handled.
    func handleURL(_ url: URL) -> Bool {
        // Custom scheme: bainluck://events/123
        // Universal link: https://bainluck.com/events/123
        let pathComponents: [String]
        let queryItems: [URLQueryItem]?

        if url.scheme == "bainluck" {
            // bainluck://events/123 → host="events", path="/123"
            var components = [url.host].compactMap { $0 }
            components += url.pathComponents.filter { $0 != "/" }
            pathComponents = components
            queryItems = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
        } else if url.host == "bainluck.com" || url.host == "www.bainluck.com" {
            pathComponents = url.pathComponents.filter { $0 != "/" }
            queryItems = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
        } else {
            return false
        }

        guard !pathComponents.isEmpty else { return false }

        switch pathComponents[0] {
        case "events":
            if pathComponents.count >= 2, let id = Int(pathComponents[1]) {
                navigate(to: .eventDetail(id: id), tab: .feed)
                return true
            }

        case "futures":
            if pathComponents.count >= 2, let id = Int(pathComponents[1]) {
                navigate(to: .futuresDetail(id: id), tab: .feed)
                return true
            }

        case "ei":
            if pathComponents.count >= 2 && pathComponents[1] == "hall-of-fame" {
                navigate(to: .eiRankings, tab: .feed)
                return true
            }

        case "search":
            let query = queryItems?.first(where: { $0.name == "q" })?.value
            selectedTab = .search
            if let query, !query.isEmpty {
                pendingSearchQuery = query
            }
            return true

        case "my-stuff":
            selectedTab = .myStuff
            return true

        case "preferences":
            navigate(to: .preferences, tab: .myStuff)
            return true

        case "category":
            if pathComponents.count >= 2 {
                let key = pathComponents[1]
                let name = sportCategories.first(where: { $0.id == key })?.name ?? key.capitalized
                navigate(to: .sportCategory(key: key, name: name), tab: .feed)
                return true
            }

        default:
            break
        }

        return false
    }

    /// Switch to a tab and push a route after a brief delay for animation.
    func navigate(to route: Route, tab: AppTab) {
        selectedTab = tab
        // Brief delay to let tab switch animate before pushing
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.pendingRoute = route
        }
    }

    /// Consume the pending route (called by the active tab view).
    func consumeRoute() -> Route? {
        let route = pendingRoute
        pendingRoute = nil
        return route
    }

    /// Consume the pending search query (called by SearchView).
    func consumeSearchQuery() -> String? {
        let query = pendingSearchQuery
        pendingSearchQuery = nil
        return query
    }
}
