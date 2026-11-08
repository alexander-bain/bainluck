#if os(macOS)
import AppKit

/// #10880 — "Add to Calendar…" on the Mac. It writes the game's .ics
/// (``CalendarICS10880``) to the app's temporary folder and opens it with the
/// reader's calendar app, which shows the event for review.
///
/// Nothing here touches EventKit: no access request, no save, no read. Opening
/// the file is the whole handoff. Its only signal is whether macOS could open
/// the file, so a failure says Calendar didn't open and a success says nothing.
/// Whether the reader added the event is for Calendar to know.
@MainActor
final class CalendarICSHandoff10880 {
    static let shared = CalendarICSHandoff10880()

    private var gate = CalendarHandoffGate10880()

    func open(_ draft: CalendarEntryDraft10880, eventID: Int, now: Date = Date()) {
        guard gate.allows(eventID: eventID, at: now) else { return }
        do {
            let file = try Self.write(draft, eventID: eventID, now: now)
            if !NSWorkspace.shared.open(file) { Self.sayCalendarDidNotOpen() }
        } catch {
            Self.sayCalendarDidNotOpen()
        }
    }

    /// One file per game, replaced on each open, in a folder of the app's own
    /// temporary directory.
    static func write(_ draft: CalendarEntryDraft10880, eventID: Int, now: Date) throws -> URL {
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("Calendar10880", isDirectory: true)
            .appendingPathComponent(String(eventID), isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let file = folder.appendingPathComponent(CalendarICS10880.fileName(for: draft))
        let document = CalendarICS10880.document(for: draft, eventID: eventID, now: now)
        try Data(document.utf8).write(to: file, options: .atomic)
        return file
    }

    private static func sayCalendarDidNotOpen() {
        let alert = NSAlert()
        alert.messageText = "Calendar didn't open"
        alert.informativeText = "Bain Luck couldn't hand this game to your calendar app. Nothing was added."
        alert.runModal()
    }
}
#endif
