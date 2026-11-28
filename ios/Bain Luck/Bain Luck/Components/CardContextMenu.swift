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
    var onShare: ((FeedItem) -> Void)?
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
        } else if let setSlug = Self.collectionSlug(for: item) {
            CollectionContextMenuItems(
                slug: setSlug,
                showsDividerBeforeShareSection: showsShareSectionDivider,
                onCopyLink: { onCopyLink?(item) },
                onShare: { onShare?(item) }
            )
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

    static func collectionSlug(for item: FeedItem) -> String? {
        if let slug = item.collection?.slug.trimmingCharacters(in: .whitespacesAndNewlines), !slug.isEmpty {
            return slug
        }
        if let slug = item.bundle?.themeCollectionRef?.slug.trimmingCharacters(in: .whitespacesAndNewlines), !slug.isEmpty {
            return slug
        }
        if let slug = item.bundle?.roundupCollectionRef?.slug.trimmingCharacters(in: .whitespacesAndNewlines), !slug.isEmpty {
            return slug
        }
        if let slug = item.bundle?.roundupContract?.machineryCard?.slug.trimmingCharacters(in: .whitespacesAndNewlines), !slug.isEmpty {
            return slug
        }
        if let setId = item.pairedMetricSet?.setId, setId.hasPrefix("oscars-") {
            return "oscars-2027"
        }
        return nil
    }

    static func copyableHomeProbability(for event: FeedEventData) -> Double? {
        guard !EventState.isFinished(event.status),
              event.heroProbabilitySource != "settled" else {
            return nil
        }
        return OpeningLineHero.currentOddsForCard(event.currentOdds, heroSource: event.heroProbabilitySource)?.homeProbability
    }

    @ViewBuilder
    private func eventMenu(_ event: FeedEventData) -> some View {
        let url = eventShareURL(event.id, style: shareURLStyle)

        if let prob = Self.copyableHomeProbability(for: event) {
            Button {
                let text = "\(event.homeTeam): \(formatProbability(prob))"
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

        #if os(iOS)
        // #10880 — a quiet utility item below Share, only on a game whose start
        // came from a schedule. Absent otherwise: no disabled item, no hint.
        if case .offer = CalendarEntry10880.decide(for: event.calendarSubject10880, now: Date()) {
            Button {
                // Asked again at the tap: a menu built before kick-off can be
                // opened after it.
                if case .offer(let draft) = CalendarEntry10880.decide(
                    for: event.calendarSubject10880, now: Date()
                ) {
                    CalendarEditorPresenter10880.shared.present(draft)
                }
            } label: {
                Label("Add to Calendar", systemImage: "calendar.badge.plus")
            }
        }
        #endif

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
                let text = "\(leader.name): \(formatProbability(prob))"
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

/// #13103 — Copy Link + Share menu items for any set / collection card, sharing
/// `https://bainluck.com/collections/<slug>`. Uses `Button` + `SetShareSheetPresenter13103`
/// rather than a menu `ShareLink` so the share tap executes its instrumentation
/// callback and `MENU_SITES` (#5525) stays unchanged.
struct CollectionContextMenuItems: View {
    let slug: String
    var showsDividerBeforeShareSection = false
    var onCopyLink: (() -> Void)?
    var onShare: (() -> Void)?
    var onLessLikeThis: (() -> Void)?

    var body: some View {
        let url = collectionShareURL(slug)

        if showsDividerBeforeShareSection {
            Divider()
        }

        Button {
            onCopyLink?()
            copyToClipboard(url)
        } label: {
            Label("Copy Link", systemImage: "link")
        }

        Button {
            onShare?()
            SetShareSheetPresenter13103.shared.present(urlString: url)
        } label: {
            Label("Share", systemImage: "square.and.arrow.up")
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
}
