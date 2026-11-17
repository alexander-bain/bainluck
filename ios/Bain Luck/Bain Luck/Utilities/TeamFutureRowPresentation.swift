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

    static func needsTotalsLineResolution(_ item: TeamFutureItem) -> Bool {
        let cleaned = cleanedMarketCaption(item.marketName)
        let isTotals = (item.canonicalMarketKey?.localizedCaseInsensitiveContains(":win_totals:") == true)
            || cleaned.range(
                of: #"\b(?:(?:win|point|goal|run)s?\s+totals?|over\s*/\s*under)\b"#,
                options: [.regularExpression, .caseInsensitive]
            ) != nil
        guard isTotals else { return false }
        let hasDigitInOutcome = item.outcomeName.range(of: #"\d"#, options: .regularExpression) != nil
        let hasDigitInCaption = cleaned.range(of: #"\d"#, options: .regularExpression) != nil
        return !hasDigitInOutcome && !hasDigitInCaption
    }

    static func resolveAvatar(forSubjectTitle subjectTitle: String, item: TeamFutureItem, team: TeamPageTeam) -> Avatar {
        let fallbackCrestURL = httpsURL(item.matchedTeam?.logoSmall ?? team.logoSmall ?? team.logoLarge)
        let fallbackAbbr = team.abbreviation ?? TeamShortName.abbreviation(team.name)
        let fallbackHex = item.matchedTeam?.primaryColor ?? team.primaryColor

        if !outcomeNamesTeam(subjectTitle, team: team, matchedTeam: item.matchedTeam),
           let member = matchRosterMember(named: subjectTitle, team: team),
           let headshotURL = httpsURL(member.headshot) {
            return .playerHeadshot(
                url: headshotURL,
                position: member.position,
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

    /// Builds a 1.0.7 team-page futures row, returning `nil` when an unquantified totals
    /// container (`"Regular Season Win Totals"`) carries no line even after detail lookup
    /// so no row ever prints a bare percentage without naming what it is the chance of.
    static func fastCutRow12823(
        _ item: TeamFutureItem,
        team: TeamPageTeam,
        resolvedOutcomeName: String? = nil
    ) -> FastCutRow12823? {
        let base = row(item)
        let cleanedCaption = cleanedMarketCaption(base.caption)
        let effectiveOutcome = (resolvedOutcomeName?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
            ?? base.title

        let parsedTotals = parseTotalsLine(
            fromOutcomeName: effectiveOutcome,
            cleanedCaption: cleanedCaption,
            canonicalMarketKey: item.canonicalMarketKey
        )
        if needsTotalsLineResolution(item), parsedTotals.lineLabel == nil {
            return nil
        }

        let cleanOutcomeSubject = parsedTotals.cleanEntityName ?? base.title
        let baseCaptionWithLine: String
        if let lineLabel = parsedTotals.lineLabel {
            if cleanedCaption.localizedCaseInsensitiveContains("Regular Season") {
                baseCaptionWithLine = "\(lineLabel) · Regular Season"
            } else {
                baseCaptionWithLine = lineLabel
            }
        } else {
            baseCaptionWithLine = cleanedCaption
        }

        let (finalTitle, finalCaption) = rewriteWhichSubjectIfNeeded(
            outcomeName: cleanOutcomeSubject,
            cleanedCaption: baseCaptionWithLine,
            team: team,
            matchedTeam: item.matchedTeam
        )

        return FastCutRow12823(
            title: finalTitle,
            caption: finalCaption,
            settledWon: base.settledWon,
            out: base.out,
            percent: base.percent,
            rankLine: base.rankLine,
            avatar: resolveAvatar(forSubjectTitle: finalTitle, item: item, team: team)
        )
    }

    private static func parseTotalsLine(
        fromOutcomeName rawOutcome: String,
        cleanedCaption: String,
        canonicalMarketKey: String?
    ) -> (cleanEntityName: String?, lineLabel: String?) {
        let trimmed = rawOutcome.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return (nil, nil) }

        let unit: String? = {
            if canonicalMarketKey?.localizedCaseInsensitiveContains(":win_totals:") == true
                || cleanedCaption.range(of: #"\bwins?\s+totals?\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "wins"
            }
            if cleanedCaption.range(of: #"\bpoints?\s+totals?\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "points"
            }
            if cleanedCaption.range(of: #"\bgoals?\s+totals?\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "goals"
            }
            if cleanedCaption.range(of: #"\bruns?\s+totals?\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "runs"
            }
            return nil
        }()

        // e.g. "O 9.5 — New England Patriots" or "Over 9.5 — New England Patriots" or "U 9.5 — Team"
        let pattern = #"^(O|Over|U|Under)\s*(\d+(?:\.\d+)?)\s*(?:—|–|-)\s*(.+)$"#
        if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
           let match = regex.firstMatch(in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed)),
           let dirRange = Range(match.range(at: 1), in: trimmed),
           let numRange = Range(match.range(at: 2), in: trimmed),
           let entityRange = Range(match.range(at: 3), in: trimmed),
           let value = Double(trimmed[numRange]) {
            let dir = trimmed[dirRange].lowercased()
            let isOver = dir.hasPrefix("o")
            let entity = String(trimmed[entityRange]).trimmingCharacters(in: .whitespacesAndNewlines)
            let numberText = String(trimmed[numRange])
            let line = formatOverUnderLine(isOver: isOver, value: value, rawNumber: numberText, unit: unit)
            return (entity.isEmpty ? nil : entity, line)
        }

        // Already a readable threshold outcome on a totals market (e.g. "10+ wins", "Over 9.5")
        if let regex = try? NSRegularExpression(pattern: #"^(O|Over|U|Under)\s*(\d+(?:\.\d+)?)$"#, options: [.caseInsensitive]),
           let match = regex.firstMatch(in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed)),
           let dirRange = Range(match.range(at: 1), in: trimmed),
           let numRange = Range(match.range(at: 2), in: trimmed),
           let value = Double(trimmed[numRange]) {
            let isOver = trimmed[dirRange].lowercased().hasPrefix("o")
            let line = formatOverUnderLine(isOver: isOver, value: value, rawNumber: String(trimmed[numRange]), unit: unit)
            return (nil, line)
        }

        return (nil, nil)
    }

    private static func formatOverUnderLine(isOver: Bool, value: Double, rawNumber: String, unit: String?) -> String {
        let floorVal = floor(value)
        let isHalfHook = abs((value - floorVal) - 0.5) < 0.001
        let isWhole = abs(value - round(value)) < 0.001
        if let unit {
            if isOver {
                if isHalfHook {
                    return "\(Int(floorVal) + 1)+ \(unit)"
                } else if isWhole {
                    return "Over \(Int(round(value))) \(unit)"
                }
                return "Over \(rawNumber) \(unit)"
            } else {
                if isHalfHook {
                    return "\(Int(floorVal)) or fewer \(unit)"
                } else if isWhole {
                    return "Under \(Int(round(value))) \(unit)"
                }
                return "Under \(rawNumber) \(unit)"
            }
        }
        return "\(isOver ? "Over" : "Under") \(rawNumber)"
    }

    /// Fable #12847 item 1: "The row's name is its subject."
    /// Rewrites which-team markets (`"New England · Christian Barmore Next Team"` ->
    /// `"Christian Barmore"` + `"Next team: New England"`) and normalizes which-player /
    /// which-coach captions (`"Mike Vrabel"` + `"Next head coach: New England Patriots"`).
    private static func rewriteWhichSubjectIfNeeded(
        outcomeName: String,
        cleanedCaption: String,
        team: TeamPageTeam,
        matchedTeam: TeamFutureTeam?
    ) -> (title: String, caption: String) {
        let outTrimmed = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        let capTrimmed = cleanedCaption.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !outTrimmed.isEmpty, !capTrimmed.isEmpty else {
            return (outcomeName, cleanedCaption)
        }
        let lowerOut = outTrimmed.lowercased()
        guard lowerOut != "yes" && lowerOut != "no" else {
            return (outcomeName, cleanedCaption)
        }

        func stripPossessive(_ raw: String) -> String {
            raw.trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: #"(?:'s|’s)$"#, with: "", options: [.regularExpression, .caseInsensitive])
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }

        // 1. "<Player>'s Next Team" / "<Player> Next Team" / "<Player> Next Club"
        if let subject = firstCapture(
            in: capTrimmed,
            pattern: #"^(.+?)(?:'s|’s)?\s+Next\s+(?:Team|Club)(?:\s+in\s+20\d{2}(?:-\d{2,4})?)?\??$"#
        ) {
            let cleanSubj = stripPossessive(subject)
            if !cleanSubj.isEmpty, cleanSubj.caseInsensitiveCompare(outTrimmed) != .orderedSame {
                return (cleanSubj, "Next team: \(outTrimmed)")
            }
        }

        // 2. "Next Team for <Player>" / "Next Club of <Player>"
        if let subject = firstCapture(
            in: capTrimmed,
            pattern: #"^Next\s+(?:Team|Club)\s+(?:for|of)\s+(.+?)\??$"#
        ) {
            let cleanSubj = stripPossessive(subject)
            if !cleanSubj.isEmpty, cleanSubj.caseInsensitiveCompare(outTrimmed) != .orderedSame {
                return (cleanSubj, "Next team: \(outTrimmed)")
            }
        }

        // 3. "Where will <Player> play/sign/go/land/be traded..."
        if let subject = firstCapture(
            in: capTrimmed,
            pattern: #"^(?:Where|Which\s+(?:team|club))\s+will\s+(.+?)\s+(?:play|sign|go|land|be\s+traded)(?:\s+(?:for|with|to|next|in\s+20\d{2}(?:-\d{2,4})?))*\??$"#
        ) {
            let cleanSubj = stripPossessive(subject)
            if !cleanSubj.isEmpty, cleanSubj.caseInsensitiveCompare(outTrimmed) != .orderedSame {
                return (cleanSubj, "Next team: \(outTrimmed)")
            }
        }

        // 4. "Which team will draft/sign/trade for/acquire/hire <Player>?"
        if let regex = try? NSRegularExpression(
            pattern: #"^Which\s+(?:team|club)\s+will\s+(draft|sign|trade\s+for|acquire|hire)\s+(.+?)(?:\s+in\s+(?:the\s+)?20\d{2}(?:-\d{2,4})?(?:\s+[\w\s]+?)?)?\??$"#,
            options: [.caseInsensitive]
        ),
           let match = regex.firstMatch(in: capTrimmed, range: NSRange(capTrimmed.startIndex..., in: capTrimmed)),
           let verbRange = Range(match.range(at: 1), in: capTrimmed),
           let subjRange = Range(match.range(at: 2), in: capTrimmed) {
            let verb = capTrimmed[verbRange].lowercased()
            let cleanSubj = stripPossessive(String(capTrimmed[subjRange]))
            if !cleanSubj.isEmpty, cleanSubj.caseInsensitiveCompare(outTrimmed) != .orderedSame {
                let label = (verb == "draft") ? "Drafted by: \(outTrimmed)" : "Next team: \(outTrimmed)"
                return (cleanSubj, label)
            }
        }

        // 5. "<Player>'s Team After the Trade Deadline"
        if let subject = firstCapture(
            in: capTrimmed,
            pattern: #"^(.+?)(?:'s|’s)?\s+Team\s+After\s+(?:the\s+)?Trade\s+Deadline\??$"#
        ) {
            let cleanSubj = stripPossessive(subject)
            if !cleanSubj.isEmpty, cleanSubj.caseInsensitiveCompare(outTrimmed) != .orderedSame {
                return (cleanSubj, "Team after trade deadline: \(outTrimmed)")
            }
        }

        // 6. Which-person / which-coach market where outcome is already the person ("Mike Vrabel")
        //    and market is "<Team> Next Head Coach / Starting QB / General Manager".
        if !outcomeNamesTeam(outTrimmed, team: team, matchedTeam: matchedTeam),
           let regex = try? NSRegularExpression(
            pattern: #"^(.+?)(?:'s|’s)?\s+Next\s+(Head\s+Coach|Coach|Manager|General\s+Manager|GM|Starting\s+QB|Starting\s+Quarterback)\??$"#,
            options: [.caseInsensitive]
           ),
           let match = regex.firstMatch(in: capTrimmed, range: NSRange(capTrimmed.startIndex..., in: capTrimmed)),
           let clubRange = Range(match.range(at: 1), in: capTrimmed),
           let roleRange = Range(match.range(at: 2), in: capTrimmed) {
            let club = stripPossessive(String(capTrimmed[clubRange]))
            let rawRole = String(capTrimmed[roleRange])
            let roleDisplay = (rawRole.uppercased() == "GM")
                ? "GM"
                : rawRole.replacingOccurrences(of: "QB", with: "__QB__")
                    .lowercased()
                    .replacingOccurrences(of: "__qb__", with: "QB")
            if !club.isEmpty {
                return (outTrimmed, "Next \(roleDisplay): \(club)")
            }
        }

        return (outcomeName, cleanedCaption)
    }

    private static func firstCapture(in text: String, pattern: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              match.numberOfRanges >= 2,
              let r = Range(match.range(at: 1), in: text)
        else { return nil }
        return String(text[r])
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
        let shortName = TeamShortName.short(team.name, sportKey: team.sportKey)
        let teamKey = normalizePersonKey(team.name, stripSuffix: false)
        let shortKey = normalizePersonKey(shortName, stripSuffix: false)
        var derivedLocation: String?
        if !shortKey.isEmpty, teamKey.hasSuffix(" " + shortKey) {
            derivedLocation = String(teamKey.dropLast(shortKey.count + 1))
        }
        let sameClubMatchedName: String? = (matchedTeam?.id == nil || matchedTeam?.id == team.id) ? matchedTeam?.name : nil
        let candidates = [
            team.name,
            team.location,
            derivedLocation,
            shortName,
            team.abbreviation,
            sameClubMatchedName,
        ].compactMap { $0 }.map { normalizePersonKey($0, stripSuffix: false) }
        return candidates.contains(outKey)
    }

    private static func matchRosterMember(named subjectName: String, team: TeamPageTeam) -> TeamRosterMember? {
        let roster = team.rosterMembers
        guard !roster.isEmpty else { return nil }

        let subjectExact = normalizePersonKey(subjectName, stripSuffix: false)
        guard !subjectExact.isEmpty else { return nil }
        if let exact = roster.first(where: { normalizePersonKey($0.name, stripSuffix: false) == subjectExact }) {
            return exact
        }

        let subjectRelaxed = normalizePersonKey(subjectName, stripSuffix: true)
        if !subjectRelaxed.isEmpty,
           let relaxed = roster.first(where: { normalizePersonKey($0.name, stripSuffix: true) == subjectRelaxed }) {
            return relaxed
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
