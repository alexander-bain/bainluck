import SwiftUI

/// #10880 — the event page's quiet way into "Add to Calendar".
///
/// The page's toolbar holds Share and Pin and has no overflow menu, so this is
/// a small "More" menu after them, holding the one item. Share and Pin are
/// untouched and keep their places. The menu exists only while the game is
/// eligible (``CalendarEntry10880``): on any other page there is no menu, no
/// disabled item and no hint. VoiceOver reads it as "More", then the item.
///
/// It offers only when the page's served event IS the page's own id. While a
/// new page loads, or after a duplicate drains to its canonical row, the view
/// model can hold another event; an entry must link the game the reader opened,
/// the same id Share sends.
///
/// The same menu on the Mac reads "Add to Calendar…": the item opens the
/// game in the reader's calendar app for review (``CalendarHandoff10880``).
struct CalendarDetailMenu10880: View {
    let pageEventId: Int
    let event: EventDetail?

    var body: some View {
        if Self.draft(pageEventId: pageEventId, event: event, now: Date()) != nil {
            Menu {
                Button {
                    // Asked again at the tap: a menu drawn before the start
                    // can be opened after it.
                    if let draft = Self.draft(pageEventId: pageEventId, event: event, now: Date()) {
                        CalendarHandoff10880.add(draft, eventID: pageEventId)
                    }
                } label: {
                    #if os(macOS)
                    Label("Add to Calendar…", systemImage: "calendar.badge.plus")
                    #else
                    Label("Add to Calendar", systemImage: "calendar.badge.plus")
                    #endif
                }
            } label: {
                // Pin's 44 pt tap target, beside it in the same group.
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 14))
                    // `.plain` drops the toolbar's colour; keep Share's black
                    // (`.tint` painted it the accent blue, native 5d3931e735).
                    .foregroundStyle(.primary)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            // The label's frame alone left the control 48×36: the toolbar's own
            // style sizes a Menu's control, and the label only paints inside it
            // (native, f62502f156: taps 20 pt above and below centre opened
            // nothing). Pin escapes that style with `.plain`; a button-style
            // Menu takes the same, so its control is the label's 44×44.
            .menuStyle(.button)
            .buttonStyle(.plain)
            #if os(macOS)
            // Pin beside it has no chevron either.
            .menuIndicator(.hidden)
            #endif
            .accessibilityLabel("More")
        }
    }

    /// The editor's draft, or nil when the page offers nothing.
    static func draft(pageEventId: Int, event: EventDetail?, now: Date) -> CalendarEntryDraft10880? {
        guard let event, event.id == pageEventId else { return nil }
        guard case .offer(let draft) = CalendarEntry10880.decide(
            for: event.calendarSubject10880, now: now
        ) else { return nil }
        return draft
    }
}

/// #10880 — each platform's way to put a draft in front of the reader: the
/// system's own editor on iPhone and iPad (``CalendarEditorPresenter10880``),
/// and on the Mac an .ics opened in the reader's calendar app
/// (``CalendarICSHandoff10880``). Neither asks for calendar access, and
/// neither tells the reader the event was saved.
enum CalendarHandoff10880 {
    static func add(_ draft: CalendarEntryDraft10880, eventID: Int) {
        #if os(iOS)
        CalendarEditorPresenter10880.shared.present(draft)
        #elseif os(macOS)
        CalendarICSHandoff10880.shared.open(draft, eventID: eventID)
        #endif
    }
}
