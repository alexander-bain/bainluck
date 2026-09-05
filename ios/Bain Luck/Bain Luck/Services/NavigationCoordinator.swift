import Combine
import Foundation
import SwiftUI

/// Tab identifiers for programmatic tab switching.
enum AppTab: Int, Hashable {
    case feed = 0
    case discover = 1
    case leagues = 2
    case search = 3
    case myStuff = 4
    // Quick Links (iPad sidebar only — not shown as iPhone tabs)
    case futures = 5
    case weather = 6
    case economics = 7
    case politics = 8
    case entertainment = 9
    case preferences = 10
    case calibration = 11
}

/// Coordinates deep link and universal link URL handling with tab navigation.
@MainActor
final class NavigationCoordinator: ObservableObject {
    @Published var selectedTab: AppTab = .discover
    @Published var pendingRoute: Route?
    @Published var pendingSearchQuery: String?
    @Published var liveGameCount: Int = 0
    @Published var showBugReport = false
    @Published var liveGameTitle: String = "Bain Luck"

    /// Handles supported app links by selecting the destination tab and queuing any route payload.
    /// Returns `true` when the URL maps to a known Bain Luck route.
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
            // A link to the collection, not to one row. `bainluck://events` is
            // what LiveGamesWidget's tap-through and every one of its empty
            // states hand out, and what MenuBarView opens — and it used to fall
            // out of this switch and return false, so a reader who tapped a
            // widget showing three live games got the app's default tab
            // instead of the list they were looking at.
            selectedTab = .feed
            return true

        case "futures":
            if pathComponents.count >= 2, let id = Int(pathComponents[1]) {
                navigate(to: .futuresDetail(id: id), tab: .feed)
                return true
            }
            navigate(to: .futuresList, tab: .feed)
            return true

        case "ei":
            selectedTab = .feed
            return true

        case "search":
            let query = queryItems?.first(where: { $0.name == "q" })?.value
            selectedTab = .search
            if let query, !query.isEmpty {
                pendingSearchQuery = query
            }
            return true

        case "tournaments":
            // The US Open link. `bainluck.com/tournaments/<slug>` is a real web
            // page and `Route.tournamentHub` is a real screen that Browse and
            // Search both push — but this switch had no case for it, so the one
            // surface Alex shops during a Grand Slam was the one surface no link
            // could open. Routed to Browse, which is where the hub is reached by
            // hand and the tab that consumes `pendingRoute` for it (#2998).
            if pathComponents.count >= 2 {
                let slug = pathComponents[1]
                // `?name=` lets a caller that already knows the real title pass
                // it, so the title bar does not have to be guessed from a slug.
                let name = queryItems?.first(where: { $0.name == "name" })?.value
                navigate(
                    to: .tournamentHub(slug: slug, name: name ?? tournamentDisplayName(forSlug: slug)),
                    tab: .leagues
                )
                return true
            }
            // A link to the collection: Browse is the list of hubs.
            selectedTab = .leagues
            return true

        case "playoffs":
            if pathComponents.count >= 2 {
                navigate(to: .leagueGrid(slug: pathComponents[1]), tab: .leagues)
            } else {
                selectedTab = .leagues
            }
            return true

        case "my-stuff":
            selectedTab = .myStuff
            return true

        case "preferences":
            navigate(to: .preferences, tab: .myStuff)
            return true

        case "weather":
            navigate(to: .weather, tab: .feed)
            return true

        case "economics":
            navigate(to: .economics, tab: .feed)
            return true

        case "politics":
            navigate(to: .politics, tab: .feed)
            return true

        case "entertainment":
            navigate(to: .entertainment, tab: .feed)
            return true

        case "category":
            if pathComponents.count >= 2 {
                let key = pathComponents[1]
                let name = sportCategories.first(where: { $0.id == key })?.name ?? key.capitalized
                navigate(to: .sportCategory(key: key, name: name), tab: .feed)
                return true
            }

        case "daily":
            navigate(to: .dailyChallenge, tab: .discover)
            return true

        case "challenge":
            if pathComponents.count >= 2 {
                navigate(to: .friendChallenge(code: pathComponents[1]), tab: .discover)
                return true
            }

        case "calibration":
            navigate(to: .calibration, tab: .leagues)
            return true

        default:
            break
        }

        return false
    }

    /// Selects the destination tab, then queues the route after the tab transition can begin.
    func navigate(to route: Route, tab: AppTab) {
        selectedTab = tab
        // Brief delay to let tab switch animate before pushing
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.pendingRoute = route
        }
    }

    /// Returns and clears the next route waiting for the active tab view.
    func consumeRoute() -> Route? {
        let route = pendingRoute
        pendingRoute = nil
        return route
    }

    /// Returns and clears the search query captured from a deep link.
    func consumeSearchQuery() -> String? {
        let query = pendingSearchQuery
        pendingSearchQuery = nil
        return query
    }
}
