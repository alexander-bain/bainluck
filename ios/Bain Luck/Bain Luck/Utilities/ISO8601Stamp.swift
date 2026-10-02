import Foundation

/// #8651 — the one stamp shape the server writes, parsed by hand.
///
/// `String.asDate` sits under every chart, freshness check and reconciliation
/// on a game page, and a page body re-runs on every update the page takes in.
/// `ISO8601DateFormatter` costs ~37 µs a stamp on a Mac, and the stamps the server
/// actually sends (`2026-10-01T23:40:00+00:00`, no fraction, 16,419 of 18,032
/// on Steelers–Browns 14780550's history) missed the fractional formatter
/// first and were parsed twice. Measured on that game's two payloads, 22,984
/// stamps: 865 ms through the formatters, 0.6 ms here.
///
/// This is a FAST PATH, not a second parser. It accepts only
/// `YYYY-MM-DDTHH:MM:SS[.fraction](Z|±HH:MM)` with every field in range and
/// returns `nil` for anything else, so the caller falls through to the
/// formatters and gets exactly what it got before. For what it does accept it
/// returns the formatter's value bit for bit — including the formatter's
/// truncation of the fraction to whole milliseconds. The formatter's lenient
/// cases (Feb 29 in a common year, `24:00`, `+0000`) are deliberately NOT
/// accepted; they take the formatter path and keep its answer.
nonisolated enum ISO8601Stamp {
    static func date(_ stamp: String) -> Date? {
        var stamp = stamp
        return stamp.withUTF8 { parse($0) }
    }

    private static func parse(_ b: UnsafeBufferPointer<UInt8>) -> Date? {
        let n = b.count
        guard n >= 20,
              b[4] == UInt8(ascii: "-"), b[7] == UInt8(ascii: "-"), b[10] == UInt8(ascii: "T"),
              b[13] == UInt8(ascii: ":"), b[16] == UInt8(ascii: ":"),
              let century = twoDigits(b, 0), let yy = twoDigits(b, 2),
              let month = twoDigits(b, 5), let day = twoDigits(b, 8),
              let hour = twoDigits(b, 11), let minute = twoDigits(b, 14),
              let second = twoDigits(b, 17) else { return nil }
        let year = century * 100 + yy
        guard (1...12).contains(month), day >= 1, day <= daysIn(month: month, year: year),
              hour <= 23, minute <= 59, second <= 59 else { return nil }

        var i = 19
        var milliseconds = 0
        if b[i] == UInt8(ascii: ".") {
            i += 1
            var digits = 0
            while i < n, b[i] >= UInt8(ascii: "0"), b[i] <= UInt8(ascii: "9") {
                // The formatter keeps whole milliseconds and drops the rest.
                if digits < 3 { milliseconds = milliseconds * 10 + Int(b[i] - UInt8(ascii: "0")) }
                digits += 1
                i += 1
            }
            guard digits > 0 else { return nil }
            for _ in digits..<max(digits, 3) { milliseconds *= 10 }
        }

        guard i < n else { return nil }
        var offset = 0
        if b[i] == UInt8(ascii: "Z") {
            i += 1
        } else if b[i] == UInt8(ascii: "+") || b[i] == UInt8(ascii: "-") {
            guard i + 6 == n, b[i + 3] == UInt8(ascii: ":"),
                  let offsetHours = twoDigits(b, i + 1), let offsetMinutes = twoDigits(b, i + 4),
                  offsetHours <= 23, offsetMinutes <= 59 else { return nil }
            offset = (offsetHours * 3600 + offsetMinutes * 60) * (b[i] == UInt8(ascii: "+") ? 1 : -1)
            i += 6
        } else {
            return nil
        }
        guard i == n else { return nil }

        let seconds = daysFromCivil(year: year, month: month, day: day) * 86_400
            + hour * 3600 + minute * 60 + second - offset
        return Date(timeIntervalSince1970: Double(seconds) + Double(milliseconds) / 1000)
    }

    private static func twoDigits(_ b: UnsafeBufferPointer<UInt8>, _ i: Int) -> Int? {
        let tens = Int(b[i]) - 48, ones = Int(b[i + 1]) - 48
        guard (0...9).contains(tens), (0...9).contains(ones) else { return nil }
        return tens * 10 + ones
    }

    private static func daysIn(month: Int, year: Int) -> Int {
        switch month {
        case 2: return (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 ? 29 : 28
        case 4, 6, 9, 11: return 30
        default: return 31
        }
    }

    /// Days since 1970-01-01 in the proleptic Gregorian calendar (Howard
    /// Hinnant's `days_from_civil`).
    private static func daysFromCivil(year: Int, month: Int, day: Int) -> Int {
        let y = month <= 2 ? year - 1 : year
        let era = (y >= 0 ? y : y - 399) / 400
        let yearOfEra = y - era * 400
        let dayOfYear = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1
        let dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * 146_097 + dayOfEra - 719_468
    }
}
