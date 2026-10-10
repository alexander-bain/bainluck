import Foundation

/// #10830 — how the player-props browser files one player's one ladder.
///
/// The browser groups ladders into FAMILIES ("Receiving Yards", "Touchdowns")
/// so a reader can switch from one stat to the next across every player. A
/// family is navigation only: each ladder stays its own row with its own
/// rungs, so two markets are never blended into one price by sharing a pill.
///
/// The web twin groups by the same stat words (#10809's `CompactPlayerProps`).
enum PlayerPropsFamily {
    /// The family every UNPRICED ladder is filed under, last in the pill row.
    /// #5137 — a flat ladder is not a price, so it must not take a stat's
    /// place beside the priced ones; D102 keeps it reachable and out of the way.
    static let unpricedFamily = "Unpriced props"

    /// The stat words a ladder is browsed under.
    ///
    /// Drops only the parts that name a LINE rather than a stat: a leading
    /// `2+ ` and a trailing `O/U 2.5`, so "Ashton Jeanty: 2+ Touchdowns" (already
    /// "2+ Touchdowns" through `PlayerPropsStatLabel`) and the matchup's
    /// "Touchdowns" ladder share a pill. Everything else is kept verbatim —
    /// "(Protected)", "Ladder", "Escalator" name different contracts and stay
    /// different families (protected-contract separation).
    static func name(statLabel: String) -> String {
        var label = statLabel.trimmingCharacters(in: .whitespaces)
        label = label.replacingOccurrences(
            of: #"^\d+(?:\.\d+)?\+\s+"#, with: "", options: .regularExpression)
        label = label.replacingOccurrences(
            of: #"\s+O/U\s+\d+(?:\.\d+)?$"#, with: "",
            options: [.regularExpression, .caseInsensitive])
        let trimmed = label.trimmingCharacters(in: .whitespaces)
        return trimmed.isEmpty ? statLabel : trimmed
    }

    /// The family a ladder is filed under, priced or not.
    static func family(statLabel: String, isPriced: Bool) -> String {
        isPriced ? name(statLabel: statLabel) : unpricedFamily
    }

    // MARK: - Protected touchdowns (Alex 10/10)

    /// The pill a VERIFIED protected-touchdown ladder is filed under. Still its
    /// own family — a protected contract settles differently, so it never
    /// shares a pill (or a price) with the plain "Touchdowns" ladders.
    static let protectedTouchdownFamily = "Protected TDs"
    /// What the row calls the stat: the thing the contract counts.
    static let protectedTouchdownStat = "Touchdowns scored"
    static let participationRuleTitle = "Participation rule"

    /// Alex 10/10 — what the Stat chooser prints for a family. The protected
    /// family is a navigation key, never shown: its chip says what the
    /// contract counts, and ``chooserNote(family:)`` ties the rule to it so it
    /// still reads as a different choice from plain "Touchdowns".
    static func chooserTitle(family: String) -> String {
        family == protectedTouchdownFamily ? protectedTouchdownStat : family
    }

    /// The second line on a family's chip — the protected contract's rule
    /// name, nil for every other family.
    static func chooserNote(family: String) -> String? {
        family == protectedTouchdownFamily ? participationRuleTitle : nil
    }

    /// Kalshi's `rules_secondary` for series `KXNFLTDPROT`, in fan words.
    /// Read by Root on 2026-10-10 from the series and from both Drake Maye
    /// LV–NE markets (`native-usability-20261010/kalshi-*.json`). Applies to
    /// THAT series only; another protected stat needs its own verified rule.
    static let participationRuleLines = [
        "If the player plays in the first half but not after halftime (overtime included), the market settles at its price just before kickoff — unless the player has already reached the target.",
        "If the player plays after halftime, it settles on the actual touchdowns scored.",
        "No injury or injury designation is needed for this to apply. A player who never plays falls under Kalshi's separate non-participation rule.",
        "Passing touchdowns don't count as the passer scoring.",
    ]
    /// The series' own contract terms (`contract_terms_url` in the series JSON).
    static let participationRuleTermsURL = URL(
        string: "https://assets.kalshi.com/contract_terms/NFLENTITYSTATCOVERED.pdf")!

    /// Is this ladder one whose protection rule has been read from the venue?
    /// Only Kalshi's NFL "Touchdowns (Protected)" contract. Every other
    /// "(Protected)" stat keeps its venue name verbatim and gets no
    /// explanation, because none has been verified for it.
    static func isVerifiedProtectedTouchdowns(
        statLabel: String, sportKey: String?, sources: Set<String>
    ) -> Bool {
        sportKey == "americanfootball_nfl"
            && sources == ["kalshi"]
            && name(statLabel: statLabel).lowercased() == "touchdowns (protected)"
    }

    /// Pill order: the families with the most ladders first (the stat the
    /// game is most quoted on leads), ties by name so a relaunch deals the same
    /// row (#4857), and the unpriced family always last.
    static func orderedFamilies(_ families: [String]) -> [String] {
        let counts = families.reduce(into: [String: Int]()) { $0[$1, default: 0] += 1 }
        return counts.keys.sorted { a, b in
            let aLast = a == unpricedFamily, bLast = b == unpricedFamily
            if aLast != bLast { return bLast }
            let (ca, cb) = (counts[a] ?? 0, counts[b] ?? 0)
            return ca != cb ? ca > cb : a < b
        }
    }

    /// The rung a ladder opens on: the PRICED rung nearest even odds, ties to
    /// the lower line. It is an entry point onto quoted rungs, never a derived
    /// price — nil when no rung carries a price, so nothing is selected.
    static func defaultTarget(probabilities: [Double?]) -> Int? {
        var best: (index: Int, distance: Double)?
        for (index, probability) in probabilities.enumerated() {
            guard let probability else { continue }
            let distance = abs(probability - 0.5)
            if best == nil || distance < best!.distance {
                best = (index, distance)
            }
        }
        return best?.index
    }

    /// The line a target chip prints: `2+` for a whole-number line, `2.5+`
    /// where the venue quoted a half — never rounded into a different line.
    static func targetLabel(_ threshold: Double) -> String {
        let text = threshold.rounded() == threshold
            ? String(Int(threshold))
            : String(format: "%g", threshold)
        return "\(text)+"
    }
}
