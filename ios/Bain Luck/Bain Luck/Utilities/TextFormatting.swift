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
    // #3657 — the calibration payload's source key is the bare lowercase
    // `datagolf`, and `.capitalized` rendered it "Datagolf". It lives here rather
    // than in `CalibrationViewModel.sourceDisplayNames` because it is a brand, not
    // a calibration label: every surface that title-cases a raw key now spells it
    // the way DataGolf does.
    "datagolf": "DataGolf",
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

/// Fully title-cases a lowercase / underscore-delimited key while keeping known
/// acronyms and brand tokens intact — the native mirror of
/// `frontend/lib/titleCase.ts` `toTitleCaseAcronymSafe`. Use this for category /
/// subcategory / tag keys that arrive lowercased (e.g. "pga_tour" -> "PGA Tour",
/// "mma" -> "MMA", "occunet" -> "OccuNet").
///
/// Distinct from `properTitleCase`, which only *repairs* acronyms in an already
/// cased display string and never lowercases unrecognised words. This one owns
/// the "raw lowercase key -> title" job that inline `.capitalized` / per-word
/// upper-casers used to do (and which garbled "pga" into "Pga"). It reuses the
/// same `knownAcronyms` / `brandCasing` sets so both formatters stay in sync.
nonisolated func toTitleCaseAcronymSafe(_ raw: String) -> String {
    raw
        .replacingOccurrences(of: "_", with: " ")
        .split(separator: " ", omittingEmptySubsequences: true)
        .map { word -> String in
            let token = String(word)
            let lower = token.lowercased()
            // Brand first: OccuNet must beat the OCCUNET acronym entry.
            if let brand = brandCasing[lower] { return brand }
            let bare = token.uppercased().filter { $0.isLetter || $0.isNumber }
            if !bare.isEmpty, knownAcronyms.contains(bare) { return bare }
            return lower.prefix(1).uppercased() + lower.dropFirst()
        }
        .joined(separator: " ")
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

// MARK: - Not saying the same thing twice (#3550)

/// An outcome's label with the heading directly above it removed.
///
/// Kalshi names a tennis outcome by restating its whole market and appending
/// the bit that differs: market `"US Open ATP: Francisco Cerundolo vs Alexander
/// Blockx"`, outcome `"US Open ATP: Francisco Cerundolo vs Alexander Blockx
/// Total Sets: O/U 3.5"`. `SpecialEventMarketsView` prints the market name as
/// the mini-card's heading and then prints each outcome underneath it, so on a
/// page already titled *Blockx vs Cerundolo* the reader gets those 52 characters
/// a fifteenth time, and the three words that actually distinguish the row —
/// `Match O/U 36.5` from `Set 1 O/U 9.5` from `Set Handicap +/-1.5` — arrive at
/// the end of a wrapped second line. Every such row is twice as tall as it
/// needs to be, for nothing.
///
/// Measured on production 2026-09-06 over open markets on events in
/// −1d…+7d: **260 outcome rows across 25 events** restate their own market
/// name, in six shapes (`Set N O/U N`, `Set N Winner`, `Match O/U N`,
/// `Total Sets: O/U N`, `Set Handicap +/-N`, `Game Spread +/-N`) — and **every
/// one of them is tennis**. No other sport has a single row like it, which is
/// why this is a display rule about a heading rather than a venue quirk worth
/// special-casing by name.
///
/// **Two guards, both of which turn a tidy-up into a defect if omitted:**
/// 1. The remainder must begin at a WORD BOUNDARY. A heading `"Set 1"` against
///    an outcome `"Set 10 Winner"` would otherwise leave `"0 Winner"` — a label
///    that is not merely ugly but says a different, wrong thing.
/// 2. A remainder that is empty gives back the ORIGINAL. An outcome named
///    exactly its market renders as a blank row otherwise, and a blank row
///    beside a live percentage reads as data we failed to load.
///
/// Anything that does not match is returned untouched, which is the common case
/// across every other sport.
///
/// **This is the Swift half of `frontend/lib/otherMarketGroups.ts`
/// (`stripCardPrefix`), which fixed the same rows on web in live/065 (#2746)
/// after Alex hit them on the Pegula–Fernandez match.** The two must print the
/// same string for the same row — including the colon that `Total Sets: O/U
/// 2.5` drops — because they are two pictures of one question, and #3503 is
/// this codebase's standing receipt for what happens when one surface's copy
/// rule moves and the other's does not.
///
/// It diverges from web in exactly one way, deliberately: web anchors a regex
/// built from the market's tokens and has no word-boundary check, so a heading
/// `"Set 1"` over an outcome `"Set 10 Winner"` yields `"0 Winner"` there. That
/// is latent rather than live (no venue serves that pair today) and is filed
/// against web, not worked around here — guard 1 below is the behaviour both
/// surfaces should end up with.
nonisolated func labelWithoutRedundantHeading(_ outcomeName: String, under heading: String) -> String {
    let outcome = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
    let head = heading.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !head.isEmpty, outcome.count > head.count,
          outcome.lowercased().hasPrefix(head.lowercased())
    else { return outcomeName }

    let remainder = outcome.dropFirst(head.count)
    // Guard 1 — the heading has to have ended on a whole word.
    guard let boundary = remainder.first, !boundary.isLetter, !boundary.isNumber else {
        return outcomeName
    }

    // Web's `PREFIX_JOINERS`, same character set: a venue joins parent to child
    // with a bare space (tennis), a colon, a middot or a pipe.
    let trimmed = remainder
        .trimmingCharacters(in: CharacterSet(charactersIn: " :·-|\u{2013}\u{2014}"))
        .trimmingCharacters(in: .whitespacesAndNewlines)
    // Guard 2 — never hand back a blank row.
    guard !trimmed.isEmpty else { return outcomeName }

    // Web's `COLON_BEFORE_OU`: `Total Sets: O/U 2.5` → `Total Sets O/U 2.5`.
    // The colon was punctuation joining the venue's own two halves; with the
    // heading gone it reads as a label introducing a value, which it is not.
    return trimmed.replacingOccurrences(
        of: #":\s+(?=O/U\b)"#,
        with: " ",
        options: .regularExpression
    )
}
