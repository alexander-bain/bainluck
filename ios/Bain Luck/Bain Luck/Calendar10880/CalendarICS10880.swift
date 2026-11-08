import Foundation

/// #10880 — the Mac's way into Calendar: one game as an iCalendar file
/// (RFC 5545) that the reader's calendar app opens for review.
///
/// The Mac has no EventKitUI editor, and asking for calendar access to write
/// the entry ourselves is the one thing the iPhone path is built to avoid. An
/// opened .ics keeps the same promise: Calendar shows the event, the reader
/// picks a calendar and adds it or doesn't, and Bain Luck never learns which.
/// So the app never says "saved".
///
/// Everything in the file comes from the ``CalendarEntryDraft10880`` the
/// iPhone editor opens with: the title, the served start, the planning length,
/// the link Share sends and the notes. Nothing is re-derived here.
///
/// - The start and end are UTC instants (`…Z`). The start is the served
///   instant; the end adds the planning length in elapsed seconds, so a game
///   across a daylight-saving change keeps its real length, and Calendar shows
///   both in the reader's own zone.
/// - TEXT values are escaped (backslash, semicolon, comma, line break). Every
///   line is folded at 75 octets without splitting a character, and lines end
///   in CRLF (RFC 5545 §3.1, §3.3.11).
/// - The UID is the game's, so opening the file again for the same game hands
///   Calendar the same event rather than a second one. It claims nothing about
///   what the reader's calendar already holds.
nonisolated enum CalendarICS10880 {

    static func document(for draft: CalendarEntryDraft10880, eventID: Int, now: Date) -> String {
        let lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Bain Luck//Add to Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            "UID:event-\(eventID)@bainluck.com",
            "DTSTAMP:\(utc(now))",
            "DTSTART:\(utc(draft.start))",
            "DTEND:\(utc(draft.end))",
            "SUMMARY:\(text(draft.title))",
            "DESCRIPTION:\(text(draft.notes))",
            "URL:\(draft.url.absoluteString)",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return lines.flatMap(fold).joined(separator: "\r\n") + "\r\n"
    }

    /// The file's name in Finder and in Calendar's import sheet: the title,
    /// without the characters a file name can't hold.
    static func fileName(for draft: CalendarEntryDraft10880) -> String {
        let cleaned = draft.title
            .map { "/:\\\n\r".contains($0) ? "-" : $0 }
            .reduce(into: "") { $0.append($1) }
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let stem = cleaned.isEmpty ? "Bain Luck game" : String(cleaned.prefix(80))
        return stem + ".ics"
    }

    /// RFC 5545 §3.3.11: backslash, semicolon and comma are escaped, and a line
    /// break of any kind becomes `\n`.
    static func text(_ value: String) -> String {
        var out = ""
        for character in value {
            switch character {
            case "\\": out += "\\\\"
            case ";": out += "\\;"
            case ",": out += "\\,"
            case "\r\n", "\n", "\r": out += "\\n"
            default: out.append(character)
            }
        }
        return out
    }

    /// RFC 5545 §3.1: no line longer than 75 octets. A continuation starts with
    /// one space, which counts, so it carries 74. Breaks fall between
    /// characters, never inside one's UTF-8 bytes.
    static func fold(_ line: String) -> [String] {
        var lines: [String] = []
        var current = ""
        var octets = 0
        for character in line {
            let size = String(character).utf8.count
            let limit = lines.isEmpty ? 75 : 74
            if octets + size > limit, !current.isEmpty {
                lines.append(current)
                current = ""
                octets = 0
            }
            current.append(character)
            octets += size
        }
        lines.append(current)
        return lines.enumerated().map { $0.offset == 0 ? $0.element : " " + $0.element }
    }

    /// `20261108T211500Z`: Gregorian, UTC, whole seconds.
    static func utc(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? .gmt
        let c = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
        return String(format: "%04d%02d%02dT%02d%02d%02dZ",
                      c.year ?? 0, c.month ?? 0, c.day ?? 0, c.hour ?? 0, c.minute ?? 0, c.second ?? 0)
    }
}

/// One handoff at a time on the Mac.
///
/// Each open puts an import sheet in front of the reader, so a double click
/// would stack two sheets for one game. The second request for the same game
/// inside the window is refused. Another game, or the same one later, opens.
/// It knows nothing about entries already in the reader's calendar.
nonisolated struct CalendarHandoffGate10880: Sendable, Equatable {
    static let window: TimeInterval = 3

    private(set) var lastEventID: Int?
    private(set) var lastOpenedAt: Date?

    mutating func allows(eventID: Int, at now: Date) -> Bool {
        if lastEventID == eventID, let lastOpenedAt {
            let elapsed = now.timeIntervalSince(lastOpenedAt)
            if elapsed >= 0, elapsed < Self.window { return false }
        }
        lastEventID = eventID
        lastOpenedAt = now
        return true
    }
}
