import Foundation

/// #11666 / #12307 — the soccer three-way helpers the event-page headline
/// (`EventSportHeadlines12472`) shares with the soccer story cards: the
/// Home/Draw/Away roles, how an outcome label maps to one, and Ruling 49-A's
/// field scaling. Pure logic, no views, so the App Clip can carry the headline
/// without the event page's cards. The cards live in
/// `Components/EventAtlasSoccerCards11666.swift` as an extension of this type.
nonisolated enum EventAtlasSoccerCards11666 {

    static func openChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    static func scaleThreeWayField(
        home: Double?,
        draw: Double?,
        away: Double?
    ) -> (home: Double?, draw: Double?, away: Double?, rawSum: Double?) {
        guard let h = openChance(home),
              let d = openChance(draw),
              let a = openChance(away) else {
            return (nil, nil, nil, nil)
        }
        let sum = h + d + a
        guard sum >= 0.90 else {
            return (nil, nil, nil, sum)
        }
        return (h / sum, d / sum, a / sum, sum)
    }

    // MARK: - 1. Three-Way Match Outcome roles

    nonisolated enum ThreeWayRole: String, Equatable, Sendable {
        case home
        case draw
        case away
    }

    // MARK: - Soccer Club Side Resolution

    static let clubAffixPattern: NSRegularExpression? = try? NSRegularExpression(
        pattern: #"\b(?:fc|afc|cf|sc|ac|sv|bv|vfb|vfl|rb|tsg|fsv|bsc|ud|cd|rcd|rc|fk|sk|nk|if|bk|ik|\d{2,4})\b"#,
        options: [.caseInsensitive]
    )

    static func stripSoccerClubAffixes(_ value: String) -> String {
        let range = NSRange(value.startIndex..<value.endIndex, in: value)
        let stripped = clubAffixPattern?.stringByReplacingMatches(in: value, options: [], range: range, withTemplate: " ") ?? value
        return stripped
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: ",", with: " ")
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    static func tokenContains(_ text: String, target: String) -> Bool {
        let a = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let b = target.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !a.isEmpty, !b.isEmpty else { return false }
        if a == b { return true }
        let aTokens = Set(a.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 })
        let bTokens = Set(b.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 })
        guard !aTokens.isEmpty, !bTokens.isEmpty else { return false }
        return aTokens.isSubset(of: bTokens) || bTokens.isSubset(of: aTokens)
    }

    static func resolveSoccerSide(
        candidate: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> ThreeWayRole? {
        let c = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !c.isEmpty else { return nil }
        let lower = c.lowercased()
        if lower == homeTeam.lowercased() || lower == homeShort.lowercased() { return .home }
        if lower == awayTeam.lowercased() || lower == awayShort.lowercased() { return .away }

        let rawHome = tokenContains(c, target: homeTeam) || tokenContains(c, target: homeShort)
        let rawAway = tokenContains(c, target: awayTeam) || tokenContains(c, target: awayShort)
        if rawHome && !rawAway { return .home }
        if rawAway && !rawHome { return .away }
        if rawHome && rawAway { return nil }

        let strippedC = stripSoccerClubAffixes(c)
        let strippedHome = stripSoccerClubAffixes(homeTeam)
        let strippedHomeShort = stripSoccerClubAffixes(homeShort)
        let strippedAway = stripSoccerClubAffixes(awayTeam)
        let strippedAwayShort = stripSoccerClubAffixes(awayShort)
        guard !strippedC.isEmpty else { return nil }

        let sHome = tokenContains(strippedC, target: strippedHome) || tokenContains(strippedC, target: strippedHomeShort)
        let sAway = tokenContains(strippedC, target: strippedAway) || tokenContains(strippedC, target: strippedAwayShort)
        if sHome && !sAway { return .home }
        if sAway && !sHome { return .away }
        return nil
    }

    static func classifyThreeWayRole(
        outcomeLabel: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> ThreeWayRole? {
        let trimmed = outcomeLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.range(of: #"^(?:draw|tie)(?:\b|\s*\()"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .draw
        }
        let cleaned = trimmed.replacingOccurrences(
            of: #"\s+wins$"#,
            with: "",
            options: [.regularExpression, .caseInsensitive]
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        return resolveSoccerSide(
            candidate: cleaned,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort
        )
    }
}
