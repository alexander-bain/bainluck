import Foundation

// MARK: - Acronym-aware title casing

/// Tokens that should be fully upper-cased when they appear as a whole word,
/// regardless of how the source string was cased. Backend strings sometimes
/// arrive `.capitalized` (e.g. "Rbc Canadian Open"), which garbles acronyms
/// and brand names. `properTitleCase` restores them.
nonisolated private let knownAcronyms: Set<String> = [
    // Leagues / governing bodies
    "PGA", "LPGA", "DP", "LIV", "NBA", "WNBA", "NHL", "MLB", "NFL",
    "NCAA", "NCAAB", "NCAAF", "MLS", "UCL", "MMA", "UFC", "NASCAR",
    "F1", "PGA", "US", "USA", "UK", "EU", "UAE", "ATP", "WTA",
    // Brands / sponsors that show up in tournament names
    "RBC", "AT&T", "BMW", "FedEx", "TPC", "CJ", "WM", "3M", "ISCO",
    "RSM", "ZOZO", "AON", "KPMG", "PNC", "DSW", "TGL", "OCCUNET",
]

/// Mixed-case brand tokens that must be preserved exactly when matched
/// case-insensitively. Title casing or upper casing would otherwise garble them.
nonisolated private let brandCasing: [String: String] = [
    "att": "AT&T",
    "at&t": "AT&T",
    "fedex": "FedEx",
    "occunet": "OccuNet",
    "mcilroy": "McIlroy",
    "mcilroy's": "McIlroy's",
    "wgc": "WGC",
    "ihop": "IHOP",
]

/// Title-cases a string while preserving / restoring known acronyms and
/// mixed-case brand tokens. Use this for tournament, category, and league
/// names that may arrive from the backend already `.capitalized` (which
/// garbles "RBC" -> "Rbc", "McIlroy" -> "Mcilroy", etc.).
///
/// This intentionally does NOT lower-case tokens it does not recognise, so
/// genuinely correct mixed-case input ("U.S. Open") is left untouched.
nonisolated func properTitleCase(_ raw: String) -> String {
    let words = raw.split(separator: " ", omittingEmptySubsequences: false)
    let fixed = words.map { fixWord(String($0)) }
    return fixed.joined(separator: " ")
}

nonisolated private func fixWord(_ word: String) -> String {
    guard !word.isEmpty else { return word }

    // Preserve trailing punctuation (e.g. "Open," or "RBC.").
    let trimmed = word.trimmingCharacters(in: .punctuationCharacters)
    let lower = trimmed.lowercased()

    if let brand = brandCasing[lower] {
        return word.replacingOccurrences(of: trimmed, with: brand)
    }

    if knownAcronyms.contains(trimmed.uppercased()) {
        return word.replacingOccurrences(of: trimmed, with: trimmed.uppercased())
    }

    return word
}

// MARK: - Date formatting

nonisolated(unsafe) private let _isoFractional: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

nonisolated(unsafe) private let _isoPlain: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

nonisolated private let _simpleDate: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    return f
}()

nonisolated private let _monthDay: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d"
    return f
}()

nonisolated private let _dayOnly: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "d"
    return f
}()

/// Parse a backend date string. Handles full ISO-8601 with offset and optional
/// fractional seconds (e.g. "2026-09-24T00:00:00+00:00") and bare "yyyy-MM-dd".
nonisolated func parseFlexibleDate(_ raw: String?) -> Date? {
    guard let raw, !raw.isEmpty else { return nil }
    if let d = _isoFractional.date(from: raw) { return d }
    if let d = _isoPlain.date(from: raw) { return d }
    return _simpleDate.date(from: raw)
}

/// Format a single backend date string as a compact "MMM d" (e.g. "Sep 24").
nonisolated func formattedShortDate(_ raw: String?) -> String? {
    guard let date = parseFlexibleDate(raw) else { return nil }
    return _monthDay.string(from: date)
}

/// Format a start/end backend date range as a compact design-system string:
/// "Sep 24-27" (same month), "Sep 24 - Oct 1" (cross-month), or just the
/// single end that is present. Returns nil when neither end parses.
nonisolated func formatDateRange(start: String?, end: String?) -> String? {
    let startDate = parseFlexibleDate(start)
    let endDate = parseFlexibleDate(end)

    switch (startDate, endDate) {
    case let (s?, e?):
        let cal = Calendar.current
        let sameMonth = cal.isDate(s, equalTo: e, toGranularity: .month)
            && cal.isDate(s, equalTo: e, toGranularity: .year)
        if sameMonth {
            // "Sep 24-27"
            return "\(_monthDay.string(from: s))\u{2013}\(_dayOnly.string(from: e))"
        }
        // "Sep 24 - Oct 1"
        return "\(_monthDay.string(from: s)) \u{2013} \(_monthDay.string(from: e))"
    case let (s?, nil):
        return _monthDay.string(from: s)
    case let (nil, e?):
        return _monthDay.string(from: e)
    case (nil, nil):
        return nil
    }
}
