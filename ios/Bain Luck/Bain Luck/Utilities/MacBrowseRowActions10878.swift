import Foundation
import SwiftUI

/// #10878 / #4942 / #5400 — what a right-click on a Mac League (`SportCategoryView`)
/// or Team (`TeamDetailView`) browse row offers, decided from the row's canonical
/// `Route` and optional pin state so it can be verified deterministically without
/// mounting a live macOS desktop menu.
///
/// - A game (`.eventDetail(id:)`) offers `Pin`/`Unpin` (when `isPinned` is supplied),
///   `Copy Link`, `Share`, and `Open in New Window` (opening the typed `Game`
///   `WindowGroup(for: Int.self)` scene).
/// - A market (`.futuresDetail(id:)`) offers `Pin`/`Unpin` (when `isPinned` is
///   supplied), `Copy Link`, and `Share` (no `Open in New Window`, because markets
///   do not have a dedicated typed window scene).
/// - Every other destination (`.golfTournament`, `.tournamentHub`, `.teamDetail`,
///   `.conceptCard`, etc.) returns `[]` so no empty or broken menu is attached.
///
/// No `Copy Probability` item is offered here for the same truth reason as
/// `MacSearchResultAction10878`: league and team rows include settled games,
/// 3-way draw-priced soccer matches (#5271), and team-oriented probabilities (#6444),
/// so copying an unlabeled truncated integer would violate probability/settlement honesty.
enum MacBrowseRowAction10878: Hashable, Sendable {
    case togglePin(isPinned: Bool, type: String, id: Int)
    case copyLink(String)
    case share(URL)
    case openInNewWindow(eventID: Int)

    /// Canonical pin target (`type`, `id`) for routes that `PinManager` supports.
    static func pinTarget(for route: Route) -> (type: String, id: Int)? {
        switch route {
        case .eventDetail(let id):
            return ("event", id)
        case .futuresDetail(let id):
            return ("future", id)
        default:
            return nil
        }
    }

    /// The items a row's right-click menu shows, in menu order.
    /// Empty means the row gets no context menu at all.
    static func actions(for route: Route, isPinned: Bool? = nil) -> [MacBrowseRowAction10878] {
        switch route {
        case .eventDetail(let id):
            let link = eventShareURL(id, style: .plain)
            var result: [MacBrowseRowAction10878] = []
            if let isPinned {
                result.append(.togglePin(isPinned: isPinned, type: "event", id: id))
            }
            result.append(contentsOf: [
                .copyLink(link),
                .share(shareURL(link)),
                .openInNewWindow(eventID: id),
            ])
            return result
        case .futuresDetail(let id):
            let link = futuresShareURL(id, style: .plain)
            var result: [MacBrowseRowAction10878] = []
            if let isPinned {
                result.append(.togglePin(isPinned: isPinned, type: "future", id: id))
            }
            result.append(contentsOf: [
                .copyLink(link),
                .share(shareURL(link)),
            ])
            return result
        default:
            return []
        }
    }

    var title: String {
        switch self {
        case .togglePin(let isPinned, _, _):
            return isPinned ? "Unpin" : "Pin"
        case .copyLink:
            return "Copy Link"
        case .share:
            return "Share"
        case .openInNewWindow:
            return "Open in New Window"
        }
    }

    var systemImage: String {
        switch self {
        case .togglePin(let isPinned, _, _):
            return isPinned ? "bookmark.slash" : "bookmark"
        case .copyLink:
            return "link"
        case .share:
            return "square.and.arrow.up"
        case .openInNewWindow:
            return "macwindow.badge.plus"
        }
    }

    private static func shareURL(_ link: String) -> URL {
        URL(string: link) ?? bainLuckFallbackURL
    }
}

extension View {
    /// Attaches the Mac right-click context menu for a game or market row on
    /// `SportCategoryView` or `TeamDetailView`. On iOS/iPadOS this is a no-op so
    /// shared phone/tablet behavior is untouched.
    @ViewBuilder
    func macBrowseRowMenu(_ route: Route, pinManager: PinManager? = nil) -> some View {
        #if os(macOS)
        modifier(MacBrowseRowMenu10878(route: route, pinManager: pinManager))
        #else
        self
        #endif
    }
}

#if os(macOS)
private struct MacBrowseRowMenu10878: ViewModifier {
    let route: Route
    let pinManager: PinManager?
    @Environment(\.openWindow) private var openWindow

    @ViewBuilder
    func body(content: Content) -> some View {
        let isPinned: Bool? = {
            guard let pinManager,
                  let target = MacBrowseRowAction10878.pinTarget(for: route) else {
                return nil
            }
            return pinManager.isPinned(type: target.type, id: target.id)
        }()
        let actions = MacBrowseRowAction10878.actions(for: route, isPinned: isPinned)
        if actions.isEmpty {
            content
        } else {
            content.contextMenu {
                ForEach(actions, id: \.self) { action in
                    menuItem(for: action)
                }
            }
        }
    }

    @ViewBuilder
    private func menuItem(for action: MacBrowseRowAction10878) -> some View {
        switch action {
        case .togglePin(_, let type, let id):
            Button {
                pinManager?.togglePin(type: type, id: id)
            } label: {
                Label(action.title, systemImage: action.systemImage)
            }
            Divider()
        case .copyLink(let link):
            Button {
                copyToClipboard(link)
            } label: {
                Label(action.title, systemImage: action.systemImage)
            }
        case .share(let url):
            ShareLink(item: url) {
                Label(action.title, systemImage: action.systemImage)
            }
        case .openInNewWindow(let eventID):
            Button {
                openWindow(value: eventID)
            } label: {
                Label(action.title, systemImage: action.systemImage)
            }
        }
    }
}
#endif
