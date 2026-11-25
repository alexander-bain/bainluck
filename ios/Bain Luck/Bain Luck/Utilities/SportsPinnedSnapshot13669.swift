import Foundation

/// #13669 — Snapshot of pinned item IDs held steady for the active Sports tab visit.
///
/// Tapping the pin bookmark (or swiping to pin) on the Sports tab writes to
/// `PinManager` immediately so the card's bookmark state reflects the save in place,
/// while the top `Pinned` section stays frozen until explicit navigation or refresh
/// (`onAppear`, category filter switch, pull-to-refresh, or account change) so cards
/// never jump downward or upward under the reader's finger (#13643).
nonisolated struct SportsPinnedSnapshot13669: Equatable, Sendable {
    var eventIDs: Set<Int>
    var futuresIDs: Set<Int>

    init(eventIDs: Set<Int> = [], futuresIDs: Set<Int> = []) {
        self.eventIDs = eventIDs
        self.futuresIDs = futuresIDs
    }

    func pinnedItems(in filteredItems: [FeedItem]) -> [FeedItem] {
        filteredItems.filter { item in
            if item.type == "event", let event = item.event {
                return eventIDs.contains(event.id)
            } else if item.type == "futures", let futures = item.futures {
                return futuresIDs.contains(futures.id)
            }
            return false
        }
    }
}
