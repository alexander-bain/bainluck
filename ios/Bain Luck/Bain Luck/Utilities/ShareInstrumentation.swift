import Foundation
import SwiftUI

/// Where a reader opened a share sheet from. #5525.
///
/// The raw value is the `source` column on `/api/feed/interactions`, so a read
/// of `discover_interactions` can tell the surfaces apart instead of seeing one
/// undifferentiated "share" — or, as it did until this shipped, nothing at all.
///
/// One home for the vocabulary because the string is the whole value of the
/// row: a site that invents its own spelling ("eventDetail", "detail",
/// "event-detail") does not fail, it just lands in a bucket nobody counts.
nonisolated enum ShareSurface: String, CaseIterable, Sendable {
    /// The share icon in a Discover card's footer.
    case discoverCard = "card"
    /// The share button in the event page's toolbar.
    case eventDetail = "event_detail"
    /// Either share button on the futures page — toolbar or hero.
    case futuresDetail = "futures_detail"
}

/// The one place a share is recorded from a surface that has no feed
/// personalization profile of its own. #5525.
///
/// 🔴 THE HOLE THIS CLOSES. Every share button a reader can actually see is a
/// declarative `ShareLink`, and `ShareLink` exposes no callback — so no share
/// button on this app had ever written a row. `discover_interactions` held
/// three `action='share'` rows ALL TIME when this was written, every one of
/// them `surface='web'`. The native zero was read as "nobody shares from the
/// phone"; it was "nothing on the phone can say that they did".
///
/// ✅ AND WHY IT RECORDS "OPENED", NOT "SHARED". A `ShareLink` tap presents the
/// system sheet and reports nothing afterwards — not the activity chosen, not
/// whether the reader cancelled. Writing `action: "share"` for a tap therefore
/// names an intent we observed, not a send we did not. The next read of this
/// table should say "share sheet opened" out loud; the row cannot support more
/// than that, and a report that claims more is claiming it about the tap.
///
/// Discover's own cards do NOT come through here: they route their `onShare`
/// through `DiscoverView.recordInteraction`, which writes the same row AND
/// feeds the category interaction profile. A share from a card is a
/// personalization signal; a share from a detail page has no feed context to be
/// a signal about.
nonisolated enum ShareInstrumentation {

    /// Builds the interaction row for a share-sheet open.
    ///
    /// Separated from ``recordShareOpened(itemType:itemId:itemName:category:surface:)``
    /// so the row's shape is testable without a network stub — the part that can
    /// be silently wrong (the action name, the surface string, the `source`
    /// spelling) is the part with no side effects.
    static func shareOpenedEvent(
        itemType: String,
        itemId: String,
        itemName: String?,
        category: String?,
        surface: ShareSurface
    ) -> DiscoverInteractionEvent {
        DiscoverInteractionEvent(
            action: "share",
            itemType: itemType,
            itemId: itemId,
            // "other" and not a fresh word: `category` is non-optional on the
            // wire, `DiscoverCategory` resolves every uncategorised item to
            // "other", and the endpoint's own default for an absent category is
            // "other" too. A third spelling here would be a bucket with one
            // writer and no reader.
            category: category ?? "other",
            itemName: itemName,
            score: nil,
            rank: nil,
            surface: "native",
            source: surface.rawValue
        )
    }

    /// Records that a reader opened the share sheet on a detail page.
    ///
    /// Fire-and-forget, like every other interaction write in this app: a failed
    /// analytics POST must never surface to a reader who just wanted to send a
    /// link to a friend.
    static func recordShareOpened(
        itemType: String,
        itemId: String,
        itemName: String?,
        category: String?,
        surface: ShareSurface
    ) {
        let event = shareOpenedEvent(
            itemType: itemType,
            itemId: itemId,
            itemName: itemName,
            category: category,
            surface: surface
        )
        // `feed_card_action`, not a new event name: `AnalyticsPrivacy` enforces
        // an event-name allowlist and drops anything outside it SILENTLY, so a
        // freshly minted `share_opened` would have been the same zero this ship
        // exists to end, one layer further out. `surface` carries the honest
        // answer instead.
        AnalyticsService.trackDiscoverCardAction(
            action: event.action,
            itemId: event.itemId,
            itemType: event.itemType,
            category: event.category,
            source: event.source ?? surface.rawValue,
            surface: "detail"
        )
        Task {
            _ = try? await APIClient.shared.recordDiscoverInteraction(event)
        }
    }
}

// MARK: - The one way a share button is observed

extension View {

    /// Observes a tap on a `ShareLink` without changing what the tap does.
    ///
    /// 🔴 WHY A SIMULTANEOUS GESTURE AND NOT A BUTTON. The obvious fix is to
    /// replace each `ShareLink` with a `Button` that presents
    /// `UIActivityViewController` and read `completionWithItemsHandler`, which
    /// would also distinguish *completed* from *cancelled*. That trades a
    /// working share affordance on five surfaces for an analytics row: it
    /// re-implements the system sheet, loses `ShareLink`'s own link preview and
    /// drag-out, needs a parallel macOS branch, and puts presentation state in
    /// five views that do not have any today. Reliability is priority #1 and
    /// this is instrumentation — so the share itself is left exactly as it is
    /// and the tap is merely *watched*. If the gesture ever fails to fire, the
    /// cost is the zero we already have, not a broken button.
    ///
    /// `simultaneousGesture` and not `onTapGesture`: the latter REPLACES the
    /// button's own tap handling, which would silently stop the sheet opening —
    /// the one outcome this must never cause.
    ///
    /// ⚠️ NOT USABLE INSIDE A MENU. A `ShareLink` in a `.contextMenu { }` is
    /// rendered by UIKit as a `UIMenu` element, out of the SwiftUI gesture
    /// system, so this modifier is inert there. The four menu share items
    /// (`CardContextMenu`, `MyStuffView`) are therefore still uninstrumented and
    /// are tracked separately; they need the Button-and-sheet rewrite above,
    /// scoped to the low-traffic path where its cost is worth paying.
    func recordsShareOpened(_ record: @escaping () -> Void) -> some View {
        simultaneousGesture(TapGesture().onEnded { record() })
    }
}
