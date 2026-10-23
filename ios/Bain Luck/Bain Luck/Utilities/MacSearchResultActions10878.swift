import Foundation

/// #10878 — what a right-click on a Mac Search result offers, decided from the
/// row's canonical route alone so it can be checked without SwiftUI.
///
/// A game gets Copy Link, Share and Open in New Window (the typed game window
/// Sports and My Stuff already open, so the new window is as independent as
/// one opened there); a market gets Copy Link and Share. Every other
/// destination — team, tournament, collection — gets no menu: there is no
/// native share URL for those yet, and an empty menu is worse than none.
///
/// No Copy Probability: a search row prints its number by rules
/// (#4306/#4967/#5363/#8640) and a settled row prints a score or verdict, so a
/// copied number needs its own truth tests first. Labels and symbols are
/// `CardContextMenu`'s, so a reader sees the same items on Search as on Sports.
enum MacSearchResultAction10878: Hashable {
    case copyLink(String)
    case share(URL)
    case openInNewWindow(eventID: Int)

    /// The items a row's right-click shows, in menu order. Empty means the row
    /// gets no menu at all.
    static func actions(for route: Route) -> [MacSearchResultAction10878] {
        switch route {
        case .eventDetail(let id):
            let link = eventShareURL(id)
            return [.copyLink(link), .share(shareURL(link)), .openInNewWindow(eventID: id)]
        case .futuresDetail(let id):
            let link = futuresShareURL(id)
            return [.copyLink(link), .share(shareURL(link))]
        default:
            return []
        }
    }

    var title: String {
        switch self {
        case .copyLink: return "Copy Link"
        case .share: return "Share"
        case .openInNewWindow: return "Open in New Window"
        }
    }

    var systemImage: String {
        switch self {
        case .copyLink: return "link"
        case .share: return "square.and.arrow.up"
        case .openInNewWindow: return "macwindow.badge.plus"
        }
    }

    private static func shareURL(_ link: String) -> URL {
        URL(string: link) ?? bainLuckFallbackURL
    }
}
