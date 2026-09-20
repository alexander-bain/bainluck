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

// MARK: - Tournament dates are DAYS, not instants (#6666)

/// How many whole calendar days separate a tournament's declared start day from
/// `now`, counted the way a reader counts them: 0 is the day itself, 1 the day
/// after, negative before it. Nil when the value cannot be read.
///
/// Both sides are reduced to a calendar day before subtracting — the day the
/// wire value NAMES, and the reader's today — so the answer changes at local
/// midnight and nowhere else. The elapsed-interval form this replaces
/// (`dateComponents([.day], from: startInstant, to: now)`) subtracted two
/// instants, so west of UTC it rolled over at 17:00 local instead.
///
/// `CalendarDeadline.displayDay` is the single discriminator for "is this wire
/// value a declared day or a real instant" (#4081); a second one here is how two
/// surfaces come to disagree about what day it is. A value that IS a real
/// instant keeps the reader's zone, which is correct for it.
///
/// `calendar` is a parameter so a guard can ask the question from Los Angeles
/// and from Kiritimati without moving the process it runs in — under a UTC
/// harness the local-vs-UTC shift is zero and the obvious assertion is vacuous
/// on the fix and the bug alike (gotcha #44 wearing a timezone).
nonisolated func backendDayOffset(from raw: String?, to now: Date, calendar: Calendar = .current) -> Int? {
    guard let day = CalendarDeadline.displayDay(raw, localZone: calendar.timeZone),
          let named = calendar.date(
              from: DateComponents(year: day.year, month: day.month, day: day.day)
          )
    else { return nil }
    return calendar.dateComponents(
        [.day],
        from: calendar.startOfDay(for: named),
        to: calendar.startOfDay(for: now)
    ).day
}

/// Which round of a tournament `now` falls in — 1...`roundCount` — or nil when
/// the tournament has not started, has finished, or declares no start day.
///
/// Lives here rather than inside `TournamentHeroCard` so the rule can be asked
/// at a stated instant. A round number is a function of the clock, and a clock
/// surface whose rule reads `Date()` inside a view body can only be guarded
/// against whatever today happens to be.
nonisolated func tournamentRoundNumber(
    start: String?,
    now: Date,
    calendar: Calendar = .current,
    roundCount: Int = 4
) -> Int? {
    guard let daysSinceStart = backendDayOffset(from: start, to: now, calendar: calendar),
          daysSinceStart >= 0, daysSinceStart < roundCount
    else { return nil }
    return daysSinceStart + 1
}

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
///
/// ## Why this does not simply parse and format (#6666)
///
/// A tournament's `start_date` is a **date**, and the midnight attached to it is
/// an artifact of how the server writes it down: `app/routes/golf.py` builds the
/// value as `f"{t.start_date}T00:00:00+00:00"` from a date column, and on
/// production 2026-09-20 **212 of 212** `/api/golf` date values carried exactly
/// that suffix. Read in the reader's own zone, `2026-09-17T00:00:00+00:00` is
/// 17:00 on the 16th in Pacific time, so every golf date in the app printed a
/// day early anywhere west of UTC — both ends of the range, on the Golf page's
/// hero, on every tour row, and on the tournament page. East of UTC it was
/// right, which is why it survived so many glances.
///
/// So each end is resolved to the day it DISPLAYS as, through the one helper
/// that knows the difference between a declared day and a real instant
/// (`CalendarDeadline`, #4081). A declared day renders in UTC; anything that is
/// genuinely an instant keeps the reader's zone. That discrimination is why the
/// fix is not a timezone on `_monthDay` — that formatter also serves
/// `formattedShortDate`, whose population is mixed (`event_concept.py`
/// serialises `start_date or commence_time`), and pinning it to UTC would push
/// an evening kickoff a day *late*. It is likewise not a change to
/// `parseFlexibleDate`: `FeaturedTournaments.isBeingPlayed` reads
/// `liveThrough: "2026-09-14T06:00:00+00:00"` through it, a genuine instant
/// chosen for its hour, and a parse-level shift would quietly move the Browse
/// live/resting clock.
///
/// The month comparison uses the same resolved days it prints from: comparing
/// in one calendar while printing from another picks the "Sep 30 - Oct 1" shape
/// for a range the reader then sees inside one month.
///
/// `localZone` is the zone the INSTANT branch renders in, defaulted to the
/// reader's, and exists so a guard can pin a western zone — under a UTC harness
/// the shift is zero and the obvious assertion cannot tell the fix from the bug.
nonisolated func formatDateRange(start: String?, end: String?, localZone: TimeZone = .current) -> String? {
    let startDay = CalendarDeadline.displayDay(start, localZone: localZone)
    let endDay = CalendarDeadline.displayDay(end, localZone: localZone)
    let startText = CalendarDeadline.format(start, style: .monthDay, localZone: localZone)
    let endText = CalendarDeadline.format(end, style: .monthDay, localZone: localZone)

    switch (startDay, endDay) {
    case let (s?, e?):
        guard let startText, let endText else { return startText ?? endText }
        if s.year == e.year && s.month == e.month {
            // "Sep 24-27"
            return "\(startText)\u{2013}\(e.day)"
        }
        // "Sep 24 - Oct 1"
        return "\(startText) \u{2013} \(endText)"
    case (_?, nil):
        return startText
    case (nil, _?):
        return endText
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
