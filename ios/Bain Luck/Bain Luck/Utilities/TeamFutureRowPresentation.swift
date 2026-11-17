import Foundation

/// What one team-page "Season Futures" row may say, from one place.
///
/// #9091 — seen on the Red Sox page (2026-09-27): the row printed only
/// `market_name`, so "Gold Glove: AL Center Field 98%" read as the TEAM's chance
/// when it is Ceddanne Rafaela's (17 of the 30 rows served for Boston name a
/// player or another subject). And "MLB: Team to make postseason 100% #1 of 30"
/// was served `is_winner: true` — a settled result drawn as a live price with a
/// rank, because the model never decoded `is_winner`.
///
/// This is the Swift half of `frontend/components/TeamFutureRow.tsx`, whose
/// three rules it mirrors: the OUTCOME is the headline and the market is the
/// caption; a graded winner is a result (`✓ Won`, no rank); and the live number
/// goes through the app's boundary formatter, never a bare round (#7710 — a
/// priced 0.004 must not print `0%`). `TeamFutureRowWebParity9091Tests` reads
/// the web file so the two cannot drift apart silently.
enum TeamFutureRowPresentation {

    struct Row: Equatable {
        /// The subject the price is about — a player, a team, a city.
        let title: String
        /// The question, e.g. "Gold Glove: AL Center Field".
        let caption: String
        /// A graded winner, or a club the grid says has won the question
        /// (#11493). Settled means settled: drawn as a result.
        let settledWon: Bool
        /// #11493 — the grid says the club is out of this question. Drawn as
        /// ``outBadge`` with no number and no rank, never as `<1%`.
        var out: Bool = false
        /// Nil when the row has no probability; the row then prints no number.
        let percent: String?
        /// "#1 of 9". Nil for a settled row — a rank is a claim about a race
        /// still being run — and nil when either half is missing.
        let rankLine: String?
    }

    /// The badge a settled row wears. Web's `✓ Won`, verbatim.
    static let wonBadge = "✓ Won"

    /// #11493 — the badge an eliminated row wears, in place of its number.
    static let outBadge = "Out"

    static func row(_ item: TeamFutureItem) -> Row {
        let graded = item.isWinner == true
        let verdict = graded ? nil : item.gridVerdict
        let settledWon = graded || verdict == .won
        let out = verdict == .eliminated

        let percent: String?
        if verdict != nil {
            // #11493 — the price under a grid verdict is the venue's residual
            // quote (0.001 for a club already out), not a chance. The grid draws
            // ✓/✕ with no number; so does this row.
            percent = nil
        } else if let p = item.probability {
            // A graded winner prints its served value as the result it is;
            // `formatProbability` would hedge an exact 1.0 to `>99%`.
            percent = settledWon ? "\(percentNumber(p * 100))%" : formatProbability(p)
        } else {
            percent = nil
        }

        var rankLine: String?
        if !settledWon, !out, let rank = item.rank, let total = item.totalOutcomes {
            rankLine = "#\(rank) of \(total)"
        }

        return Row(
            title: item.outcomeName,
            caption: item.marketName,
            settledWon: settledWon,
            out: out,
            percent: percent,
            rankLine: rankLine
        )
    }

    // MARK: - #12823 Team-Page 1.0.7 Fast Cut (Headshots + Crest Fallback, Prefix Strip, No Venue Labels)

    enum Avatar: Equatable, Sendable {
        case playerHeadshot(url: URL, position: String?, fallbackCrestURL: URL?, fallbackAbbr: String, fallbackHex: String?)
        case teamCrest(url: URL?, abbreviation: String, primaryHex: String?)
    }

    struct FastCutRow12823: Equatable, Sendable {
        let title: String
        let caption: String
        let settledWon: Bool
        let out: Bool
        let percent: String?
        let rankLine: String?
        let avatar: Avatar
    }

    /// Strips redundant sport/fantasy/league + season-year prefixes (`"Pro Football: 2026-27 "`,
    /// `"Fantasy Football: 2026-27 "`, `"NBA: 2026-27 "`, etc.) so team-page rows lead with the
    /// actual stat or milestone without cutting off at the right edge, while leaving genuine
    /// award prefixes like `"Gold Glove: AL Center Field"` untouched.
    static func cleanedMarketCaption(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return raw }

        var s = trimmed
        s = s.replacingOccurrences(
            of: #"^(?:(?:Pro|Fantasy|College)\s+(?:Football|Basketball|Baseball|Hockey|Soccer)|NFL|NBA|MLB|NHL|MLS|WNBA|NCAAF|NCAAB)\s*:\s*"#,
            with: "",
            options: [.regularExpression, .caseInsensitive]
        )
        s = s.replacingOccurrences(
            of: #"^Pro\s+(?:Football|Basketball|Baseball|Hockey|Soccer)\s+(?=(?:Playoffs?|Week\s+\d+)\b)"#,
            with: "",
            options: [.regularExpression, .caseInsensitive]
        )
        let withoutYear = s.replacingOccurrences(
            of: #"^20\d{2}(?:-\d{2,4})?\s+"#,
            with: "",
            options: [.regularExpression]
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        if !withoutYear.isEmpty {
            s = withoutYear
        }
        let cleaned = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? trimmed : cleaned
    }

    static func resolveAvatar(for item: TeamFutureItem, team: TeamPageTeam) -> Avatar {
        let fallbackCrestURL = httpsURL(item.matchedTeam?.logoSmall ?? team.logoSmall ?? team.logoLarge)
        let fallbackAbbr = team.abbreviation ?? TeamShortName.abbreviation(team.name)
        let fallbackHex = item.matchedTeam?.primaryColor ?? team.primaryColor
        let namesTeam = outcomeNamesTeam(item.outcomeName, team: team, matchedTeam: item.matchedTeam)

        if let member = matchRosterMember(for: item, team: team),
           let headshotURL = httpsURL(member.headshot) {
            return .playerHeadshot(
                url: headshotURL,
                position: namesTeam ? nil : member.position,
                fallbackCrestURL: fallbackCrestURL,
                fallbackAbbr: fallbackAbbr,
                fallbackHex: fallbackHex
            )
        }

        return .teamCrest(
            url: fallbackCrestURL,
            abbreviation: fallbackAbbr,
            primaryHex: fallbackHex
        )
    }

    static func fastCutRow12823(_ item: TeamFutureItem, team: TeamPageTeam) -> FastCutRow12823 {
        let base = row(item)
        return FastCutRow12823(
            title: base.title,
            caption: cleanedMarketCaption(base.caption),
            settledWon: base.settledWon,
            out: base.out,
            percent: base.percent,
            rankLine: base.rankLine,
            avatar: resolveAvatar(for: item, team: team)
        )
    }

    private static func httpsURL(_ raw: String?) -> URL? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty,
              let url = URL(string: raw),
              url.scheme?.lowercased() == "https"
        else { return nil }
        return url
    }

    private static func normalizePersonKey(_ raw: String, stripSuffix: Bool) -> String {
        let folded = raw
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
        let cleaned = folded.replacingOccurrences(
            of: #"[^a-z0-9\s]"#,
            with: "",
            options: .regularExpression
        )
        var tokens = cleaned.split(whereSeparator: \.isWhitespace).map(String.init)
        if stripSuffix, tokens.count >= 3, let last = tokens.last,
           ["jr", "sr", "ii", "iii", "iv", "v"].contains(last) {
            tokens.removeLast()
        }
        return tokens.joined(separator: " ")
    }

    private static func outcomeNamesTeam(_ outcomeName: String, team: TeamPageTeam, matchedTeam: TeamFutureTeam?) -> Bool {
        let outKey = normalizePersonKey(outcomeName, stripSuffix: false)
        guard !outKey.isEmpty else { return false }
        let candidates = [
            team.name,
            team.abbreviation,
            matchedTeam?.name,
        ].compactMap { $0 }.map { normalizePersonKey($0, stripSuffix: false) }
        if candidates.contains(outKey) { return true }
        let teamKey = normalizePersonKey(team.name, stripSuffix: false)
        return teamKey.hasPrefix(outKey + " ") || teamKey.hasSuffix(" " + outKey)
    }

    private static func matchRosterMember(for item: TeamFutureItem, team: TeamPageTeam) -> TeamRosterMember? {
        guard let roster = team.roster, !roster.isEmpty else { return nil }

        let outcomeExact = normalizePersonKey(item.outcomeName, stripSuffix: false)
        if let exact = roster.first(where: { normalizePersonKey($0.name, stripSuffix: false) == outcomeExact }) {
            return exact
        }

        let outcomeRelaxed = normalizePersonKey(item.outcomeName, stripSuffix: true)
        if !outcomeRelaxed.isEmpty,
           let relaxed = roster.first(where: { normalizePersonKey($0.name, stripSuffix: true) == outcomeRelaxed }) {
            return relaxed
        }

        // Team-outcome market about a specific roster player (e.g. "Christian Barmore Next Team" -> "New England").
        if outcomeNamesTeam(item.outcomeName, team: team, matchedTeam: item.matchedTeam) {
            let marketNorm = " " + normalizePersonKey(item.marketName, stripSuffix: false) + " "
            let sortedByLength = roster.sorted { $0.name.count > $1.name.count }
            for member in sortedByLength {
                let memberKey = normalizePersonKey(member.name, stripSuffix: false)
                guard memberKey.contains(" ") else { continue }
                if marketNorm.contains(" " + memberKey + " ") {
                    return member
                }
            }
        }
        return nil
    }
}

/// What one team-page "Championship Path" step prints in place of its number.
///
/// #11493 — the step stays on the page when the grid says the club is out: it
/// is the title question answered, and dropping it would let the Season Futures
/// list below draw the same market's 0.001 again (``TeamDivisionRace/
/// seasonFutures(_:championshipPath:race:sportKey:)`` hides a futures row only
/// behind a path step that answers it).
enum ChampionshipPathPresentation {

    enum Value: Equatable {
        /// The grid says the club is out — ``TeamFutureRowPresentation/outBadge``.
        case out
        /// The grid says the club won — ``TeamFutureRowPresentation/wonBadge``.
        case won
        /// A live number.
        case percent(String)
        /// Nothing to print.
        case none
    }

    static func value(_ entry: ChampionshipPathEntry) -> Value {
        switch entry.gridVerdict {
        case .eliminated: return .out
        case .won: return .won
        case nil:
            guard let p = entry.probability else { return .none }
            return .percent("\(Int(round(p * 100)))%")
        }
    }
}
