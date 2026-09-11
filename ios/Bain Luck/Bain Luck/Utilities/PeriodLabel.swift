import Foundation

/// The single implementation of ESPN period-string → chart-chip label.
///
/// #1832. This logic existed in THREE places: `OddsChartView`,
/// `ScoreDifferentialChartView`, and web's `lib/periodMarkers.ts`. The two Swift
/// copies had already drifted — the ScoreDifferential copy was missing the
/// plain-ordinal inning branch (`"3rd"`) and all three golf branches (`R1`,
/// `Round 2`, `playoff`) — so the two charts stacked on the SAME event page
/// could label the same period differently, or one could label it and the other
/// fall through to the raw string.
///
/// That is gotcha #128's shape exactly: a rule living in N consumers has N
/// verdicts, and the healthier copy is what hides the broken one. The copies are
/// deleted rather than synchronised; a second implementation that still works is
/// a second implementation that drifts again.
///
/// Web's `lib/periodMarkers.ts` is a THIRD copy and speaks a different
/// vocabulary on purpose-by-accident (`"Top 3rd"` → `T3` there, `3rd` here;
/// it also emits `/Q1` end-forms iOS has never had). Unifying that would change
/// a surface with no reported defect, so it is filed (#1834) rather than done
/// blind here. What IS enforced: exactly one implementation on the iOS side,
/// asserted by `frontend/__tests__/ios/periodLabelSingleSource.test.ts`, which
/// reads the Swift sources.
enum PeriodLabel {

    /// Normalize an ESPN period string to a short, self-explaining chip label.
    ///
    /// Returns `""` for anything that is not a period the reader should see —
    /// callers treat empty as "no chip".
    ///
    /// - Parameter sport: the event's sport key (`americanfootball_nfl`, …),
    ///   used for one thing only — completing a BARE period number, which is the
    ///   one input that does not name its own unit. See ``barePeriodUnit``.
    ///   Optional and backward-compatible: without it a bare number renders
    ///   exactly as it did before, so no existing caller changes behaviour by
    ///   not passing one.
    static func normalize(_ raw: String, sport: String? = nil) -> String {
        var s = raw.trimmingCharacters(in: .whitespaces)

        // Reject pre-game date strings like "Wed, March 25th at 10:00 PM EDT".
        // These leak from ESPN status_detail during game transitions.
        let months = "January|February|March|April|May|June|July|August|September|October|November|December"
        if s.range(of: months, options: [.regularExpression, .caseInsensitive]) != nil { return "" }
        if s.range(of: #"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\bat\b"#, options: [.regularExpression, .caseInsensitive]) != nil { return "" }

        // Strip clock prefix: "11:05 - 1st Quarter" → "1st Quarter"
        if let dashRange = s.range(of: #"^[\d.:]+\s*-\s*"#, options: .regularExpression) {
            s = String(s[dashRange.upperBound...])
        }

        // Strip "End of " / "Start of " prefix
        if let prefixRange = s.range(of: #"^(?:end|start)\s+of\s+"#, options: [.regularExpression, .caseInsensitive]) {
            s = String(s[prefixRange.upperBound...])
        }

        let lower = s.lowercased()

        // Halftime
        if lower == "halftime" || lower == "half time" || lower == "ht" { return "HT" }

        // Overtime variants
        if lower == "overtime" || lower == "ot" { return "OT" }
        if let match = lower.range(of: #"^(\d+)\w*\s+overtime$"#, options: .regularExpression) {
            return "OT\(s[match].filter(\.isNumber))"
        }

        // Basketball / Football quarters: "1st Quarter" → "Q1"
        if let match = s.range(of: #"^(\d+)\w*\s+[Qq]uarter$"#, options: .regularExpression) {
            return "Q\(s[match].filter(\.isNumber))"
        }
        // Plain ordinals for quarters
        if lower == "1st" { return "Q1" }
        if lower == "2nd" { return "Q2" }
        if lower == "3rd" { return "Q3" }
        if lower == "4th" { return "Q4" }

        // Hockey periods: "1st Period" → "P1"
        if let match = s.range(of: #"^(\d+)\w*\s+[Pp]eriod$"#, options: .regularExpression) {
            return "P\(s[match].filter(\.isNumber))"
        }

        // Soccer halves: "1st Half" → "1H"
        if let match = s.range(of: #"^(\d+)\w*\s+[Hh]alf$"#, options: .regularExpression) {
            return "\(s[match].filter(\.isNumber))H"
        }

        // Baseball innings: "Top 3rd" / "Bottom 3rd" / "Middle 3rd" → "3rd".
        //
        // Ruling 5 (explain or remove): this used to return a BARE DIGIT, so a
        // baseball chart's chip strip read "0 8" — two unlabelled numbers with
        // nothing saying they were innings. An ordinal is one character longer
        // and explains itself.
        if let match = s.range(of: #"^(?:top|bottom|mid|middle|end)\s+(\d+)"#, options: [.regularExpression, .caseInsensitive]) {
            return inning(s[match].filter(\.isNumber))
        }

        // Plain ordinal inning: "3rd" → "3rd"
        if let match = s.range(of: #"^(\d+)(?:st|nd|rd|th)$"#, options: [.regularExpression, .caseInsensitive]) {
            return inning(s[match].filter(\.isNumber))
        }

        // Golf round labels: "R1", "R2", "R3", "R4", "PO" (playoff)
        if s.range(of: #"^R\d$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return s.uppercased()
        }
        if let rMatch = s.range(of: #"^[Rr]ound\s+(\d+)$"#, options: .regularExpression) {
            return "R\(s[rMatch].filter(\.isNumber))"
        }
        if lower == "playoff" { return "PO" }

        // Already short: "Q1", "P2", "1H", "OT", "OT1", etc.
        //
        // The bare-integer arm of this pattern is what let a raw "0" through as
        // a chip reading "0" — a period number of zero is "not started", never
        // something to label. `inning()` drops it.
        if s.range(of: #"^(Q\d|P\d|\d+H|OT\d?|HT)$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return s.uppercased()
        }
        if s.range(of: #"^\d+$"#, options: .regularExpression) != nil {
            return barePeriod(s, sport: sport)
        }

        // Intermission
        if lower.contains("intermission") { return "INT" }

        return s
    }

    /// The label for a **scoreboard column** — `GameSegmentsView`'s "Score by
    /// period" header — as opposed to a chart chip.
    ///
    /// #3273. That card had grown its own parser, which read ESPN's clock PREFIX
    /// as the period number and headed a four-quarter football game
    /// `Q14 · Q8 · Q5 · Q1 ... Q4`. It is expressed here, on top of `normalize`,
    /// so there is still exactly ONE thing that knows how to read a period string;
    /// what differs is only the presentation, and only for two reasons:
    ///
    /// 1. **Innings are digits, not ordinals.** The column is 22pt, sized for two
    ///    digits by UX-P090's geometry — the width that keeps the TOTAL column on
    ///    a 375pt phone. `12th` does not fit where `12` does. A chart chip has the
    ///    room and keeps its self-explaining ordinal.
    /// 2. **A non-period gets no column.** `HT`, `INT`, a golf `PO` and anything
    ///    `normalize` passes through unrecognised (`"Delayed"` reached production
    ///    as a column header) are dropped. A header row is a claim about how the
    ///    game is divided; an unreadable string is not one.
    ///
    /// Deliberately takes no sport key. `basketball_ncaab` plays HALVES and
    /// `basketball_wncaab` plays QUARTERS, so any sport-prefix branch labels one
    /// of them wrong — the noun in the data is the only thing that can be right
    /// for both. Same principle as #3317: gate on what is actually being played.
    ///
    /// Returns `""` for "no column", matching `normalize`'s "no chip" contract.
    static func columnLabel(_ raw: String) -> String {
        let chip = normalize(raw)
        if chip.isEmpty || chip == "HT" || chip == "INT" || chip == "PO" { return "" }

        // "9th" -> "9". The ordinal is the chart's vocabulary, not the column's.
        if let match = chip.range(of: #"^\d+(?:st|nd|rd|th)$"#, options: [.regularExpression, .caseInsensitive]) {
            return String(chip[match].filter(\.isNumber))
        }

        // Everything a period column may legally say. Anything else is a string
        // `normalize` could not name, and is dropped rather than printed.
        if chip.range(of: #"^(?:Q\d+|P\d+|R\d+|\d+H|OT|OT\d+|\d+OT)$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return chip
        }
        return ""
    }

    /// The label for the live **status badge** — the red capsule on the event
    /// hero and on every sports feed card.
    ///
    /// #3273, found shooting the live Michigan game while fixing the card below
    /// it: the badge read **"5:11 - 1st Quarter 5:11"**. `StatusBadge` joined the
    /// raw ESPN period to `game_clock`, and the period embeds that same clock —
    /// the third consumer of this string to print it verbatim.
    ///
    /// Differs from `columnLabel` in one deliberate way: **baseball keeps its
    /// half-inning.** "Bottom 7th" tells a reader something "7th" does not, and a
    /// capsule has room for it, where a 22pt scoreboard column does not. That is
    /// also why this is not just `normalize`, which drops the qualifier.
    static func liveBadgeLabel(_ raw: String) -> String {
        var body = raw.trimmingCharacters(in: .whitespaces)

        // The badge prints the clock itself, beside this. Printing it here too is
        // the whole defect.
        if let clock = body.range(of: #"^[\d.:]+\s*-\s*"#, options: .regularExpression) {
            body = String(body[clock.upperBound...])
        }

        // "Bottom 7th" / "End 8th" — kept whole. The `\d` is what keeps
        // "End of 1st Quarter" out of this branch and on the shortening path.
        if body.range(
            of: #"^(?:top|bottom|mid|middle|end)\s+\d+"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil {
            return body
        }

        return normalize(body)
    }

    /// The one rule for printing a live period **beside its clock** — the hero
    /// capsule, the nav title, the macOS menu bar, the watch and the widget.
    ///
    /// #4880: on every live soccer match the hero read **`23' 23'`**. ESPN serves
    /// soccer's `period` and `game_clock` as the SAME string (`"25'"` / `"25'"`,
    /// measured on all three live UCL matches, 2026-09-10), and six call sites
    /// joined the pair with a space.
    ///
    /// This is #3273 recurring in the one shape its fix could not cover.
    /// ``liveBadgeLabel`` strips a clock **prefix** (`"5:11 - 1st Quarter"`),
    /// because that is what football sends; soccer's period does not CONTAIN the
    /// clock, it **equals** it, with no separator to find. The old guard tested
    /// for containment-with-a-separator and never for equality.
    ///
    /// Takes both strings because that is the only way to see the collision:
    /// `liveBadgeLabel` alone is handed one string and cannot know what is about
    /// to be printed next to it. Every caller that prints the pair goes through
    /// here, which is what makes the third recurrence unreachable rather than
    /// merely fixed — asserted across all three targets by
    /// `frontend/__tests__/ios/periodLabelSingleSource.test.ts`.
    ///
    /// Returns `nil` for "say nothing about the clock", so each surface keeps its
    /// own fallback (the badge says `LIVE`, the watch says nothing at all).
    static func liveStatusText(period: String?, gameClock: String?) -> String? {
        let label = (period.map(liveBadgeLabel) ?? "")
            .trimmingCharacters(in: .whitespaces)
        var clock = (gameClock ?? "").trimmingCharacters(in: .whitespaces)

        // A clock the reader cannot use. Baseball has none — production serves
        // `game_clock: null` on MLB (measured on 15308638), and ESPN has also
        // sent the literal `"0:00"`, which is what the guard this replaces was
        // written against. Both paths are live, so both are handled here.
        if clock == "0:00" || clock == "0" { clock = "" }

        // THE DEFECT. Drop the LABEL, never the clock: `game_clock` is the field
        // that is always a clock, where `period` is whatever ESPN chose to send.
        let parts = label.caseInsensitiveCompare(clock) == .orderedSame
            ? [clock]
            : [label, clock]

        let text = parts.filter { !$0.isEmpty }.joined(separator: " ")
        return text.isEmpty ? nil : text
    }

    // MARK: - A bare period number (#4888)

    /// What a BARE period digit means, by sport, and how far the numbering runs.
    ///
    /// #4888, handed to us by ux/1184 after Alex's 2026-09-09 iPad pass (item 6):
    /// the web's win-probability chart drew dashed rules captioned bare `3` and
    /// `4` and a reader had no way to learn they meant quarters.
    ///
    /// `"3"` alone is genuinely ambiguous — Q3 in football, P3 in hockey, the 3rd
    /// inning in baseball — so the unit cannot be recovered from the string. The
    /// caller knows the sport; this table is what that buys. Everything ELSE
    /// `normalize` handles carries its own noun (`"3rd Quarter"`, `"1st Period"`)
    /// and is read from the noun, never from here — that is why this is the only
    /// place `sport` is consulted, and why `columnLabel`'s "deliberately takes no
    /// sport key" note is untouched by this: its argument is that the noun beats
    /// the sport key wherever a noun exists (`basketball_ncaab` plays halves,
    /// `basketball_wncaab` plays quarters). A bare digit is the one case with no
    /// noun to prefer.
    ///
    /// **`regulation` is not decoration — it is what stops the table lying.**
    /// A sport's numbering runs past its regulation periods into overtime, and
    /// completing those with the regulation unit invents a period that does not
    /// exist: soccer has no `3H`, football no `Q5`. Beyond `regulation` we fall
    /// through to the ordinal, which is vague but true. (The web twin, PR #4916,
    /// has no such bound and can currently emit `3H`; reported to ux, theirs to
    /// take or leave.)
    ///
    /// **Prefix-matched and ORDER-SENSITIVE**, so `basketball_ncaab` — men's
    /// college, which plays two halves — is tested before the `basketball_` row
    /// that gives everyone else quarters. Prefixes, not substrings: as a prefix
    /// `basketball_ncaab` does not match `basketball_wncaab`, which plays
    /// quarters and must keep them.
    ///
    /// **BASEBALL IS DELIBERATELY ABSENT**, and so is every sport nobody has
    /// declared. A bare inning number cannot be completed honestly — `T3` and
    /// `B3` are different moments and the digit does not say which — so baseball
    /// keeps the self-explaining ordinal `inning()` already gives it rather than
    /// gaining a fabricated half. Same rule as `HalvesFromGap.sportPlaysInHalves`
    /// and `SportVocab`: a number in the wrong unit is worse than a vague one
    /// *because it looks sourced*.
    static let barePeriodUnit: [(prefix: String, regulation: Int, label: (Int) -> String)] = [
        ("americanfootball_", 4, { "Q\($0)" }),
        ("icehockey_", 3, { "P\($0)" }),
        ("soccer_", 2, { "\($0)H" }),
        ("basketball_ncaab", 2, { "\($0)H" }),
        ("basketball_", 4, { "Q\($0)" }),
    ]

    /// The sport-aware reading of a bare period number.
    ///
    /// Falls back to ``inning(_:)`` — the behaviour before #4888 — for baseball,
    /// for an unknown or absent sport, and for a number past the sport's
    /// regulation periods. That fallback is the direction worth guarding: a
    /// helper that hardcoded `Q` would pass any test that only checked
    /// `"3"` → `"Q3"`, and would relabel every NHL and MLB chart.
    static func barePeriod<S: StringProtocol>(_ digits: S, sport: String?) -> String {
        let fallback = inning(digits)
        guard let key = sport?.lowercased(), !key.isEmpty,
              let n = Int(digits), n > 0
        else { return fallback }
        for entry in barePeriodUnit where key.hasPrefix(entry.prefix) {
            return n <= entry.regulation ? entry.label(n) : fallback
        }
        return fallback
    }

    /// Render an inning number as a self-explaining ordinal. A non-positive or
    /// unparseable inning is not a period and yields `""` (no chip).
    static func inning<S: StringProtocol>(_ digits: S) -> String {
        guard let n = Int(digits), n > 0 else { return "" }
        return "\(n)\(ordinalSuffix(n))"
    }

    static func ordinalSuffix(_ n: Int) -> String {
        let mod100 = n % 100
        if (11...13).contains(mod100) { return "th" }
        switch n % 10 {
        case 1: return "st"
        case 2: return "nd"
        case 3: return "rd"
        default: return "th"
        }
    }
}

// MARK: - Halves inferred from a gap (#3317)

/// The `1H` / `HT` / `2H` markers a pause in the reading stream implies.
///
/// **A GAP SAYS "PLAY STOPPED". IT NEVER SAYS "THIS IS SOCCER."** That confusion
/// is the whole of #3317: `OddsChartView` inserted soccer's halves whenever it
/// held no period data and saw one gap over eight minutes, so a **Major League
/// Baseball** chart drew `1H` and `2H` — photographed on the live Giants–Mets
/// game 15296786, 2026-09-05, `artifacts-native-028/n028-BEFORE-mets.png`.
///
/// The guard that was already here only half worked, and its own comment says
/// why it was added: baseball inning markers are numeric, so soccer's `2H` used
/// to *overwrite* correct innings. Requiring `firstSeen.isEmpty` protected a
/// baseball game that HAS innings and did nothing for one that has none — and
/// empty markers plus a long pause is the ordinary shape of a televised
/// baseball game (between innings, pitching changes, replay reviews).
///
/// **MEASURED, 2026-09-05, on the eight live MLB event rows of the afternoon:**
/// two fire this inference right now (15296785 Cubs–Marlins, 872s and 638s
/// gaps, `has_period = 0`), four carry real period data and are untouched, and
/// two more were early enough not to have met the row floor yet. It is not a
/// corner case.
///
/// **THE INTENDED CASE CURRENTLY HAS NO DATA, AND THAT IS STATED RATHER THAN
/// ASSUMED.** Measured the same day: zero soccer events had any `espn_snapshots`
/// row in seven days, and `espn_history`'s supplement path only reads the `mlb`
/// and `stat_model` win-prob sources, neither of which serves soccer (of seven
/// live soccer matches sampled, one had win-prob rows at all — Kalshi, with no
/// game state). So this branch is dormant for the sport it was written for and
/// fired only on sports it was wrong about. It is GATED rather than deleted so
/// the capability survives the day soccer's stream returns; the soccer arm below
/// is therefore pinned by a fixture, never by production evidence.
///
/// The WEB has never had any of this: `frontend/lib/periodMarkers.ts` derives
/// boundaries from real period data on four sources and invents nothing. This
/// narrows a native-only invention rather than diverging from web.
enum HalvesFromGap {

    /// A pause longer than this is the candidate interval.
    static let minimumGapSeconds: TimeInterval = 480

    /// Below this many readings a single gap is a sync hiccup, not a half-time.
    static let minimumReadings = 5

    /// Whether a sport divides regulation into two halves with an interval —
    /// the only shape `1H`/`HT`/`2H` can be true of.
    ///
    /// **FAILS CLOSED.** An unrecognised or absent sport key returns `false`.
    /// Drawing no chips is an honest absence; drawing another sport's
    /// vocabulary is a number in the wrong unit, which `SportVocab`'s own thesis
    /// calls worse than an absent one *because it looks sourced*.
    ///
    /// Soccer only, deliberately. Every one of the 176 sport keys in the
    /// database that is soccer is `soccer_`-prefixed (measured 2026-09-05: 60 of
    /// them, and no non-soccer key contains `mls`/`epl`/`uefa`/`fifa`), so the
    /// substring is exact rather than approximate. Other halves sports — rugby,
    /// handball, NCAA basketball — are absent on purpose: none of them has ever
    /// reached this code, and adding a sport on a guess is the mistake this
    /// function exists to undo. Adding one when it is measured is one line.
    static func sportPlaysInHalves(_ sportKey: String?) -> Bool {
        guard let key = sportKey?.lowercased(), !key.isEmpty else { return false }
        return key.contains("soccer")
    }

    /// The halves implied by the first qualifying pause, oldest first — or `[]`,
    /// which is the usual and correct answer.
    ///
    /// Pure and total so the rule can be pinned in both directions rather than
    /// inspected through a rendered chart; `dates` need not be sorted.
    static func markers(
        sportKey: String?,
        espnDates: [Date]
    ) -> [(label: String, date: Date)] {
        guard sportPlaysInHalves(sportKey) else { return [] }
        let dates = espnDates.sorted()
        guard dates.count >= minimumReadings, let first = dates.first else { return [] }
        for index in 1..<dates.count {
            let gap = dates[index].timeIntervalSince(dates[index - 1])
            guard gap > minimumGapSeconds else { continue }
            return [
                ("1H", first),
                ("HT", dates[index - 1].addingTimeInterval(gap / 2)),
                ("2H", dates[index]),
            ]
        }
        return []
    }
}
