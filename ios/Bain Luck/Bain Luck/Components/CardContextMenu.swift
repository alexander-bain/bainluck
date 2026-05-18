import SwiftUI

struct CardContextMenuPin {
    let isPinned: Bool
    let toggle: () -> Void
}

struct CardContextMenu: View {
    let item: FeedItem
    var shareURLStyle: BainLuckShareURLStyle = .plain
    var pin: CardContextMenuPin?
    var showsShareSectionDivider = true
    var onCopyLink: ((FeedItem) -> Void)?
    var onLessLikeThis: (() -> Void)?
    #if os(macOS)
    var onOpenEventInNewWindow: ((Int) -> Void)?
    #endif

    var body: some View {
        if let pin {
            Button {
                pin.toggle()
            } label: {
                Label(pin.isPinned ? "Unpin" : "Pin", systemImage: pin.isPinned ? "bookmark.slash" : "bookmark")
            }
        }

        if let event = item.event {
            eventMenu(event)
        } else if let futures = item.futures {
            futuresMenu(futures)
        }

        if let onLessLikeThis {
            Divider()
            Button {
                onLessLikeThis()
            } label: {
                Label("Less Like This", systemImage: "hand.thumbsdown")
            }
        }
    }

    @ViewBuilder
    private func eventMenu(_ event: FeedEventData) -> some View {
        let url = eventShareURL(event.id, style: shareURLStyle)

        if let prob = event.currentOdds?.homeProbability {
            Button {
                let text = "\(event.homeTeam): \(Int(prob * 100))%"
                copyToClipboard(text)
            } label: {
                Label("Copy Probability", systemImage: "doc.on.doc")
            }
        }

        if showsShareSectionDivider {
            Divider()
        }

        Button {
            onCopyLink?(item)
            copyToClipboard(url)
        } label: {
            Label("Copy Link", systemImage: "link")
        }

        ShareLink(item: URL(string: url) ?? bainLuckFallbackURL) {
            Label("Share", systemImage: "square.and.arrow.up")
        }

        #if os(macOS)
        if let onOpenEventInNewWindow {
            Button {
                onOpenEventInNewWindow(event.id)
            } label: {
                Label("Open in New Window", systemImage: "macwindow.badge.plus")
            }
        }
        #endif
    }

    @ViewBuilder
    private func futuresMenu(_ futures: FeedFuturesData) -> some View {
        let url = futuresShareURL(futures.id, style: shareURLStyle)

        if let leader = futures.topOutcomes?.first, let prob = leader.probability {
            Button {
                let text = "\(leader.name): \(Int(prob * 100))%"
                copyToClipboard(text)
            } label: {
                Label("Copy Probability", systemImage: "doc.on.doc")
            }
        }

        if showsShareSectionDivider {
            Divider()
        }

        Button {
            onCopyLink?(item)
            copyToClipboard(url)
        } label: {
            Label("Copy Link", systemImage: "link")
        }

        ShareLink(item: URL(string: url) ?? bainLuckFallbackURL) {
            Label("Share", systemImage: "square.and.arrow.up")
        }
    }
}
