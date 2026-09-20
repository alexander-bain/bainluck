import Foundation

/// When a market's declared deadline is a CALENDAR DATE rather than an instant —
/// the iOS half of #4081.
///
/// `resolution_date` carries two different kinds of value on one wire field:
///
///   * a real intraday deadline — a market that closes at 3pm ET, a game start.
///     That is an instant, and "when does this resolve, my time" is the right
///     question to answer for it, so it keeps the reader's local zone.
///   * a semantic CALENDAR DATE serialised as a UTC-midnight instant, which is
///     the normal shape for a "by end of <period>" contract. `2026-12-31T00:00:00+00:00`
///     is not a moment anybody cares about; it is the string "December 31".
///
/// Formatting the second kind in the reader's zone lands it on the day BEFORE
/// everywhere west of UTC. Measured on production 2026-09-17: the app drew
/// **"Resolves Dec 30, 2026"** on "Who will be UFC Heavyweight champion at the
/// end of 2026?" (market 114175, wire `2026-12-31T00:00:00+00:00`), and
/// **2,887 of 34,780** open markets with a resolution date carry exactly
/// `00:00:00` UTC — so the whole class renders a day early for every reader in
/// the Americas. "Dec 30" and "Dec 31" are different answers to "is this still
/// live tomorrow?".
///
/// ## WHY THE DECLARED DAY IS LIFTED OUT OF THE STRING
///
/// Adapted from web's `formatResolvesLabel` (`frontend/lib/gameTimeLabel.ts`,
/// C270 P1), which reached this finding first and states the construction rule:
/// do NOT parse to a `Date` and then hand the formatter a zone override. Lift
/// the three integers out of the string and build the instant in UTC, so there
/// is no ambient-timezone path through the calendar-date branch to be wrong in.
/// That is not merely a fix that measures correct — it is one with no failing
/// case to measure.
///
/// Web's own `DATE_ONLY` guard does NOT cover our shape and is not what is
/// ported: it matches a bare `YYYY-MM-DD` only, and every futures market on this
/// wire sends a full timestamp. The discriminator here is the one the issue's
/// "Note for the fix" names — the instant is exactly UTC midnight — which fires
/// on the 2,887 and leaves the other 31,893 untouched.
///
/// ## THE HARNESS PINS UTC, SO THE OBVIOUS TEST IS VACUOUS
///
/// Under a UTC test environment local IS UTC, the shift is exactly zero, and an
/// assertion about the local-vs-UTC difference is green on the fix and green on
/// the bug alike (gotcha #44's shape). ``format(_:style:localZone:)`` therefore
/// takes the zone the INSTANT branch formats in, defaulted to `.current`, so a
/// guard can pin a real western zone and see the two branches disagree.
enum CalendarDeadline {

    enum Style {
        /// "Dec 31" — the card chrome form.
        case monthDay
        /// "Dec 31, 2026" — the metadata-row form.
        case monthDayYear
        /// "Wed, Dec 31" — the dense-row form, where the weekday is the thing
        /// being scanned for.
        case weekdayMonthDay
        /// "Wed, Dec 31 at 5:40 PM" for a real instant; "Wed, Dec 31" for a
        /// declared calendar date. See ``instantTemplate``.
        case weekdayMonthDayTime

        /// The form a DECLARED CALENDAR DATE takes. Never carries a time of day:
        /// a "by end of 2026" contract declares no hour, and printing one
        /// ("at 12:00 AM") invents a precision the wire value does not have.
        var template: String {
            switch self {
            case .monthDay: return "MMM d"
            case .monthDayYear: return "MMM d, yyyy"
            case .weekdayMonthDay, .weekdayMonthDayTime: return "EEE, MMM d"
            }
        }

        /// The form a REAL INSTANT takes; the same as ``template`` unless the
        /// style wants the hour, which only makes sense on the instant branch.
        var instantTemplate: String {
            switch self {
            case .weekdayMonthDayTime: return "EEE, MMM d 'at' h:mm a"
            default: return template
            }
        }
    }

    /// The declared year/month/day of a wire value that is a calendar date, or
    /// `nil` when the value is a real instant (or unparseable).
    ///
    /// Matches a bare `YYYY-MM-DD`, and a full timestamp whose time is exactly
    /// midnight UTC. A fractional part is allowed only when every digit is zero —
    /// `T00:00:00.5Z` is half a second past midnight and is an instant. A
    /// midnight in some OTHER zone (`T00:00:00+05:00`) is likewise an instant:
    /// it is not the shape this class is about.
    static func declaredDay(_ raw: String) -> (year: Int, month: Int, day: Int)? {
        let s = raw.trimmingCharacters(in: .whitespaces)
        let pattern = #"^(\d{4})-(\d{2})-(\d{2})(?:[Tt]00:00:00(?:\.0+)?(?:[Zz]|\+00:?00))?$"#
        guard let m = s.range(of: pattern, options: .regularExpression), m == s.startIndex..<s.endIndex else {
            return nil
        }
        let parts = s.prefix(10).split(separator: "-")
        guard parts.count == 3,
              let y = Int(parts[0]), let mo = Int(parts[1]), let d = Int(parts[2]),
              (1...12).contains(mo), (1...31).contains(d) else { return nil }
        return (y, mo, d)
    }

    /// Render a deadline for display, or `nil` when the value cannot be read.
    ///
    /// - Parameter localZone: the zone the INSTANT branch renders in. Defaults to
    ///   the reader's. The calendar-date branch ignores it by construction — that
    ///   is the whole point, and it is what the guards assert.
    static func format(_ raw: String?, style: Style, localZone: TimeZone = .current) -> String? {
        guard let raw else { return nil }

        if let day = declaredDay(raw) {
            var utc = Calendar(identifier: .gregorian)
            utc.timeZone = utcZone
            var comps = DateComponents()
            comps.year = day.year
            comps.month = day.month
            comps.day = day.day
            guard let date = utc.date(from: comps) else { return nil }
            return formatter(style.template, zone: utcZone).string(from: date)
        }

        guard let date = raw.asDate else { return nil }
        return formatter(style.instantTemplate, zone: localZone).string(from: date)
    }

    private static let utcZone = TimeZone(secondsFromGMT: 0)!

    private static func formatter(_ template: String, zone: TimeZone) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = template
        f.timeZone = zone
        return f
    }
}
