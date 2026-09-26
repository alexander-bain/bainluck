import SwiftUI

/// Formats a commence_time string relative to now: "Today 7:30 PM", "Tomorrow 2 PM", "Wed Mar 5".
struct RelativeTimeText: View {
    let dateString: String?
    /// Defaults to ``Style/full`` so every existing call site keeps the string
    /// it has.
    var style: Style = .full
    /// #8841 — the served `start_is_tbd`. True prints the DAY and "TBD" and no
    /// clock (see ``tbdText(for:now:relativeDays:)``); defaulted so every call
    /// site that has no such flag keeps the string it has.
    var startIsTbd: Bool = false

    /// How much of the moment to print.
    ///
    /// #6444 — `dayOnly` exists because a FINISHED row does not need a clock.
    /// Measured on the iPhone 17 shot of search for "Boston Red Sox"
    /// (`artifacts/native-6444-search/`): the full form wrapped onto a second
    /// line on three of five final rows — "Aug 28," above "4:15 PM" — because
    /// the row's left column is what is left after the score and the badge, and
    /// a settled row has both. Dropping the time is not a concession to that
    /// width: kick-off time is how you tell two UPCOMING fixtures apart, and a
    /// date is how you tell two played ones apart. Every scoreboard prints
    /// "Final · Sep 12" for the same reason.
    enum Style {
        case full
        case dayOnly
    }

    var body: some View {
        if let text = RelativeTimeText.text(
            for: dateString, style: style, startIsTbd: startIsTbd) {
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    /// The string the view draws, as a value.
    ///
    /// #6444 — lifted out of the `body` and given an injectable `now` so the
    /// rule can be tested. Three search rows reading "Boston Red Sox vs
    /// Baltimore Orioles · MLB · FINAL" with nothing else to tell them apart is
    /// a claim about what this function returns for three dates, and while it
    /// lived inside a `ViewBuilder` no test could make that claim.
    ///
    /// The day arithmetic replaces `Calendar.isDateInToday/Tomorrow/Yesterday`
    /// and is the same answer for `Calendar.current` — those three are exactly
    /// "the start-of-day difference is 0 / +1 / −1". They were replaced because
    /// they read the REAL clock internally, so an injected `now` would have
    /// moved only half the function and a test would have been a function of
    /// the day it ran (gotcha #44).
    static func text(
        for dateString: String?, now: Date = Date(), style: Style = .full,
        startIsTbd: Bool = false
    ) -> String? {
        if startIsTbd { return tbdText(for: dateString, now: now) }
        guard let dateString, let date = dateString.asDate else { return nil }
        let cal = Calendar.current
        let days = cal.dateComponents(
            [.day], from: cal.startOfDay(for: now), to: cal.startOfDay(for: date)
        ).day ?? 0
        let clock = style == .full ? " \(timeString(date))" : ""

        switch days {
        case 0: return "Today\(clock)"
        case 1: return "Tomorrow\(clock)"
        case -1: return "Yesterday\(clock)"
        case 2...6: return style == .full ? dayOfWeekString(date) : weekdayString(date)
        default: return style == .full ? dateWithMonthString(date) : monthDayString(date)
        }
    }

    /// #8841 — the start line of a game whose start time has not been
    /// announced: "Today · TBD", "Tomorrow · TBD", "Sep 29 · TBD". Nil for an
    /// absent or unparseable time, exactly like ``text(for:now:style:startIsTbd:)``.
    ///
    /// THE DAY IS REAL, THE CLOCK IS NOT. StatPal lists MLB postseason games
    /// before MLB sets their times and stamps them on the hour; the Red Sox @
    /// Yankees Wild Card games (15319235 / 15319236) sat at 20:00Z and printed
    /// "Sep 29 1:00 PM". The web prints the same words (`formatTbdStartLabel`
    /// in `frontend/lib/gameTimeLabel.ts`, PR #8873).
    ///
    /// THE DAY IS READ IN UTC, NOT THE READER'S ZONE — the web's rule, for the
    /// web's reason: a placeholder is not an instant, so there is nothing to
    /// localise, and a midnight-in-the-venue placeholder carried west lands on
    /// the previous day. "Today"/"Tomorrow" still compare against the READER's
    /// calendar day, which is the frame they are standing in.
    ///
    /// `relativeDays: false` is the event hero's form, which prints an absolute
    /// date on every other state too ("Sep 29 · TBD" even on the day).
    static func tbdText(
        for dateString: String?, now: Date = Date(), relativeDays: Bool = true
    ) -> String? {
        guard let dateString, let date = dateString.asDate else { return nil }
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let placeholder = utc.dateComponents([.year, .month, .day], from: date)
        let today = Calendar.current.dateComponents([.year, .month, .day], from: now)
        if relativeDays,
           let placeholderDay = utc.date(from: placeholder),
           let readerDay = utc.date(from: today),
           let days = utc.dateComponents([.day], from: readerDay, to: placeholderDay).day {
            if days == 0 { return "Today · TBD" }
            if days == 1 { return "Tomorrow · TBD" }
        }
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        f.timeZone = utc.timeZone
        return "\(f.string(from: date)) · TBD"
    }

    private static func timeString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f.string(from: date)
    }

    private static func dayOfWeekString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "EEE h:mm a"
        return f.string(from: date)
    }

    private static func dateWithMonthString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: date)
    }

    private static func weekdayString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: date)
    }

    private static func monthDayString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        return f.string(from: date)
    }
}
