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
    static func normalize(_ raw: String) -> String {
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
            return inning(s)
        }

        // Intermission
        if lower.contains("intermission") { return "INT" }

        return s
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
