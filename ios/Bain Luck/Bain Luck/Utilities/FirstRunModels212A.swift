import Foundation

// MARK: - Ruling 212-A — First-Run Onboarding Models (#11934, #13517)

/// Response envelope from `GET /api/events/search-suggestions`, used alongside live feeds
/// to source real, served first-run typeahead examples (Alex Point 8).
nonisolated struct SearchSuggestionEntry212A: Decodable, Equatable, Sendable {
    let query: String
    let label: String?
    let type: String?
    let eventId: Int?
    let marketId: Int?
}

nonisolated struct SearchSuggestionsResponse212A: Decodable, Sendable {
    let suggestions: [SearchSuggestionEntry212A]
}

/// Bridge reading any pending App Clip / shared-link handoff into Screens 1A and 2A (#11934 Point 12).
///
/// Train 4 (`apple/11934-app-clip-handoff`) registers `ClipHandoffSession11934.shared.activeHeadline`
/// on `activeHeadlineProvider` at startup; this bridge also reads Builder F's shared App Group
/// handoff record (`group.com.bainluck.Bain-Luck` / `bainluck.appclip.handoff.v1`) directly so
/// Screen `1A` displays `"Started from your link · …"` cleanly without taking a compile dependency
/// on Train 4's `BainLuckClip` target.
nonisolated enum FirstRunLinkHandoffBridge212A {
    static let appGroupID = "group.com.bainluck.Bain-Luck"
    static let storageKey = "bainluck.appclip.handoff.v1"
    static let bannerPrefix = "Started from your link"
    static let defaultTTL: TimeInterval = 24 * 60 * 60

    struct StoredRecord: Codable, Equatable, Sendable {
        let headline: String?
        let recordedAt: Date
    }

    @MainActor
    static var activeHeadlineProvider: (() -> String?)? = nil

    @MainActor
    static func currentHeadline(
        defaults: UserDefaults? = UserDefaults(suiteName: appGroupID),
        now: Date = Date()
    ) -> String? {
        if let provided = cleaned(activeHeadlineProvider?()) {
            return provided
        }
        return readSharedContainerHeadline(defaults: defaults, now: now)
    }

    @MainActor
    static func resolvedHeadline(
        explicit: String?,
        defaults: UserDefaults? = UserDefaults(suiteName: appGroupID),
        now: Date = Date()
    ) -> String? {
        cleaned(explicit) ?? currentHeadline(defaults: defaults, now: now)
    }

    static func readSharedContainerHeadline(
        defaults: UserDefaults? = UserDefaults(suiteName: appGroupID),
        now: Date = Date(),
        ttl: TimeInterval = defaultTTL
    ) -> String? {
        guard let data = defaults?.data(forKey: storageKey) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let record = try? decoder.decode(StoredRecord.self, from: data) else { return nil }
        let age = now.timeIntervalSince(record.recordedAt)
        guard age <= ttl, age >= -300 else { return nil }
        return cleaned(record.headline)
    }

    static func bannerText(headline: String?) -> String {
        if let clean = cleaned(headline) {
            return "\(bannerPrefix) \u{00B7} \(clean)"
        }
        return bannerPrefix
    }

    static func cleaned(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }
}

/// One real live card presented inside a first-run two-card pair (`2A` / `2B` / `2C`).
///
/// Follows Fable's Nov 16 changes and Fable's Points 1–3:
/// - built strictly from live unsettled `/api/feed` items matching what each card's own page shows,
/// - zero fabricated fallback cards or client-written causal/standing captions,
/// - probability changes always read in `"points"` (never `"pts"` or `%` of `%`),
/// - projections are whole numbers only.
nonisolated struct FirstRunCard212A: Identifiable, Equatable, Sendable {
    let id: String
    let kicker: String?
    let subtitleRight: String?
    let title: String
    let detailLine: String?
    let percent: Int
    let percentLabel: String
    let deltaPoints: Int?
    let accentHex: String
    let sfSymbol: String
    let logoUrl: String?
    let isSports: Bool
    let affinityCategory: String
    let workedMeaningLine: String?
    let followedSubject: FollowedSubject295A?
    let marketId: Int?
    let matchKeywords: [String]

    /// Category / sport SF Symbol icon (replaces truncated letter monograms).
    static func sfSymbol(forCategory category: String, isSports: Bool) -> String {
        let lower = category.lowercased()
        if lower.contains("nfl") || lower.contains("ncaaf") || lower.contains("football") {
            return "football.fill"
        }
        if lower.contains("nba") || lower.contains("ncaab") || lower.contains("basketball") {
            return "basketball.fill"
        }
        if lower.contains("nhl") || lower.contains("hockey") {
            return "hockey.puck.fill"
        }
        if lower.contains("mlb") || lower.contains("baseball") {
            return "baseball.fill"
        }
        if lower.contains("soccer") || lower.contains("epl") || lower.contains("mls") {
            return "soccerball"
        }
        if lower.contains("tennis") {
            return "tennisball.fill"
        }
        if lower.contains("golf") {
            return "figure.golf"
        }
        if lower.contains("entertainment") || lower.contains("oscar") || lower.contains("culture")
            || lower.contains("grammy") || lower.contains("music") || lower.contains("awards") {
            return "film.fill"
        }
        if lower.contains("econ") || lower.contains("fed") || lower.contains("macro") || lower.contains("finance") {
            return "chart.line.uptrend.xyaxis"
        }
        if lower.contains("tech") || lower.contains("ai") || lower.contains("science") {
            return "cpu.fill"
        }
        if lower.contains("weather") || lower.contains("climate") {
            return "cloud.sun.fill"
        }
        if lower.contains("politic") || lower.contains("election") || lower.contains("geopolitic") {
            return "building.columns.fill"
        }
        return isSports ? "sportscourt.fill" : "globe"
    }

    /// Plain-English shift copy strictly using `"points"` (never `"pts"`).
    static func shiftText(points delta: Int?, window: String? = nil) -> String? {
        guard let delta, delta != 0 else { return nil }
        let absVal = abs(delta)
        let noun = absVal == 1 ? "point" : "points"
        let arrow = delta > 0 ? "▲ up" : "▼ down"
        if let window, !window.isEmpty {
            return "\(arrow) \(absVal) \(noun) \(window)"
        }
        return "\(arrow) \(absVal) \(noun)"
    }

    /// Worked plain-English odds example shown on Pair 1 ("What N% means").
    static func workedMeaning(percent: Int) -> String {
        let outOfTen = max(1, min(9, Int((Double(percent) / 10.0).rounded())))
        if percent >= 45 && percent <= 55 {
            return "\(percent)% means about a coin flip \u{2014} roughly \(outOfTen) times in 10."
        }
        return "\(percent)% means about \(outOfTen) times in 10."
    }
}

/// Which card(s) on a pair screen the reader tapped directly (Alex Point 7).
nonisolated enum FirstRunPairSide212A: String, Hashable, CaseIterable, Sendable {
    case top
    case bottom
}

/// One step in the three-pair comparison sequence (`2A`, `2B`, `2C`).
nonisolated struct FirstRunPair212A: Identifiable, Equatable, Sendable {
    let id: String
    let promptTitle: String
    let arrivedContextPill: String?
    let topCard: FirstRunCard212A
    let bottomCard: FirstRunCard212A

    static let explicitlyNonSportsCategories: Set<String> = [
        "entertainment", "economics", "econ", "tech", "weather", "politics",
        "geopolitics", "culture", "awards", "music", "movies", "film", "tv",
        "science", "climate", "macro", "finance", "ai", "space", "crypto", "health", "world",
    ]

    static let explicitlySportsCategories: Set<String> = DiscoverCategory.sportsFeedbackCategories.union([
        "nfl", "nba", "nhl", "mlb", "ncaaf", "ncaab", "wncaab", "f1", "formula1",
        "nascar", "motogp", "ufc", "championship", "chess",
    ])

    /// League order approved for the onboarding game slot (Fable Send-back 2):
    /// NFL -> NBA -> MLB -> NHL -> college football -> men's college basketball -> top soccer.
    static func leaguePriority(for sportKey: String?) -> Int? {
        guard let raw = sportKey?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !raw.isEmpty else {
            return nil
        }
        switch raw {
        case "americanfootball_nfl":
            return 0
        case "basketball_nba":
            return 1
        case "baseball_mlb":
            return 2
        case "icehockey_nhl":
            return 3
        case "americanfootball_ncaaf", "americanfootball_ncaaf_fcs":
            return 4
        case "basketball_ncaab":
            return 5
        case "soccer_epl", "soccer_uefa_champs_league", "soccer_spain_la_liga",
             "soccer_germany_bundesliga", "soccer_italy_serie_a",
             "soccer_france_ligue_one", "soccer_usa_mls", "soccer_fifa_world_cup":
            return 6
        default:
            return nil
        }
    }

    private static let grimTopicPattern: NSRegularExpression? = {
        let terms = [
            // Crime & criminal cases
            "murder", "homicide", "convict", "convicted", "indict", "indicted",
            "arrest", "arrested", "prison", "jail", "guilty", "sentenced",
            "felony", "assault", "shooting", "shooter", "trial", "defendant",
            "trafficking", "crime", "criminal", "epstein", "clancy",
            // Death
            "die", "dies", "dead", "death", "funeral", "assassination",
            "assassinate", "suicide", "fatal", "casualties", "killed", "kill",
            // Disasters & outbreaks
            "earthquake", "tsunami", "hurricane", "tornado", "wildfire", "flood",
            "volcano", "eruption", "famine", "pandemic", "plague", "outbreak",
            "plane crash", "disaster", "catastrophe",
            // War & conflict
            "invade", "invasion", "war", "airstrike", "ceasefire", "missile",
            "nuclear", "bomb", "troops", "military", "annex", "conflict",
            "ukraine", "gaza", "hamas", "hezbollah", "coup", "terror",
        ]
        let joined = terms.map(NSRegularExpression.escapedPattern(for:)).joined(separator: "|")
        return try? NSRegularExpression(pattern: "\\b(?:\(joined))\\b", options: [.caseInsensitive])
    }()

    /// Rejects grim topics (crime, death, disaster, war) using word boundaries so
    /// words like "Awards" or "Warriors" are never misclassified (Fable Send-back 2).
    static func isGrimOrSensitiveTopic(title: String, outcomeName: String? = nil) -> Bool {
        let text = [title, outcomeName ?? ""].joined(separator: " ")
        guard let regex = grimTopicPattern else { return false }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.firstMatch(in: text, options: [], range: range) != nil
    }

    private static func matchesKeyword(_ word: String, in text: String) -> Bool {
        let escaped = NSRegularExpression.escapedPattern(for: word)
        guard let regex = try? NSRegularExpression(pattern: "\\b\(escaped)\\b", options: [.caseInsensitive]) else {
            return false
        }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return regex.firstMatch(in: text, options: [], range: range) != nil
    }

    /// Shows a non-sports category pill ONLY when the category agrees with the title;
    /// otherwise omits the pill (`nil`) rather than showing a wrong label (Fable Send-back 3).
    static func trustedNonSportsPill(categoryKey: String, title: String) -> String? {
        let cat = categoryKey.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let lowerTitle = title.lowercased()

        let awardKeywords = ["oscar", "oscars", "grammy", "grammys", "emmy", "emmys", "tony", "golden globe", "bafta", "academy award"]
        let entertainmentKeywords = [
            "film", "movie", "movies", "spotify", "album", "song", "concert",
            "coachella", "bond", "box office", "actor", "actress", "director",
            "show", "series", "snl", "game awards", "engaged", "married",
            "netflix", "streaming", "music", "artist", "gross", "opening weekend",
        ]
        let economyKeywords = [
            "economy", "fed", "rate", "rates", "inflation", "cpi", "gdp",
            "recession", "stock", "tariff", "tariffs", "jobs", "unemployment",
            "dollar", "oil", "treasury", "budget", "earnings", "ipo", "aapl", "apple",
        ]
        let techKeywords = [
            "ai", "openai", "claude", "gemini", "gpt", "anthropic", "llm",
            "apple", "google", "tesla", "spacex", "mars", "rocket", "chip",
            "nvidia", "meta", "microsoft", "amazon", "software", "model",
            "ipo", "quantum", "robot", "iphone",
        ]
        let politicsKeywords = [
            "election", "elections", "president", "presidential", "prime minister",
            "senate", "house", "governor", "mayor", "congress", "parliament",
            "vote", "ballot", "impeach", "cabinet", "secretary", "nominee",
            "party", "bill", "supreme court",
        ]
        let weatherKeywords = [
            "rain", "snow", "temperature", "high", "low", "wettest", "driest",
            "inches", "degrees", "forecast", "rainfall", "snowfall", "snows", "rains",
        ]

        switch cat {
        case "economics", "econ", "macro", "finance":
            return economyKeywords.contains { matchesKeyword($0, in: lowerTitle) } ? "ECONOMY" : nil
        case "entertainment", "awards", "movies", "film", "music", "tv":
            if awardKeywords.contains(where: { matchesKeyword($0, in: lowerTitle) }) {
                return "AWARDS"
            }
            return entertainmentKeywords.contains { matchesKeyword($0, in: lowerTitle) } ? "ENTERTAINMENT" : nil
        case "tech", "ai":
            if lowerTitle.contains("searched person") { return nil }
            return techKeywords.contains { matchesKeyword($0, in: lowerTitle) } ? "TECH" : nil
        case "politics", "elections":
            return politicsKeywords.contains { matchesKeyword($0, in: lowerTitle) } ? "POLITICS" : nil
        case "weather":
            if matchesKeyword("earthquake", in: lowerTitle)
                || matchesKeyword("volcano", in: lowerTitle)
                || matchesKeyword("tsunami", in: lowerTitle)
                || matchesKeyword("seismic", in: lowerTitle) {
                return nil
            }
            if lowerTitle.contains("°c") || lowerTitle.contains("°f")
                || weatherKeywords.contains(where: { matchesKeyword($0, in: lowerTitle) }) {
                return "WEATHER"
            }
            return nil
        default:
            return nil
        }
    }

    /// Resolves a futures market's headline probability without ever leading with `"No"`
    /// on a yes-or-no card (Fable Send-back 1).
    static func resolvePrimaryOutcome(for fut: FeedFuturesData) -> (outcomeName: String?, percent: Int, deltaPoints: Int?, isYesNo: Bool)? {
        let outcomes = fut.topOutcomes ?? []
        guard !outcomes.isEmpty else { return nil }

        let mTypeLower = (fut.marketType ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let lowerNames = Set(outcomes.map { $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
        let isBinaryYesNoByNames = !lowerNames.isEmpty && lowerNames.isSubset(of: ["yes", "no"])
        let hasYesOrNoPair = lowerNames.contains("yes") && lowerNames.contains("no")
        let isYesNo = mTypeLower == "yes_no" || mTypeLower == "claim" || isBinaryYesNoByNames || hasYesOrNoPair

        func computeDelta(_ move: Double?, invert: Bool) -> Int? {
            guard let move, move.isFinite else { return nil }
            let scaled = abs(move) <= 1.0 ? move * 100.0 : move
            let diff = Int((invert ? -scaled : scaled).rounded())
            return diff == 0 ? nil : diff
        }

        if isYesNo {
            if let yesOut = outcomes.first(where: { $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "yes" }),
               let pct = resolvedPercent(rawProb: yesOut.probability, servedRenderedPercent: yesOut.renderedPercent) {
                return (nil, pct, computeDelta(yesOut.movement, invert: false), true)
            }
            if let noOut = outcomes.first(where: { $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "no" }),
               let noPct = resolvedPercent(rawProb: noOut.probability, servedRenderedPercent: noOut.renderedPercent) {
                let yesProb = noOut.probability.map { p in p > 1.0 ? (100.0 - p) : (1.0 - p) }
                let yesRend = 100 - noPct
                if let yesPct = resolvedPercent(rawProb: yesProb, servedRenderedPercent: yesRend) {
                    return (nil, yesPct, computeDelta(noOut.movement, invert: true), true)
                }
            }
            return nil
        }

        let first = outcomes[0]
        let firstNameLower = first.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard firstNameLower != "no" else { return nil }
        guard let pct = resolvedPercent(rawProb: first.probability, servedRenderedPercent: first.renderedPercent) else {
            return nil
        }
        return (
            FirstRunLinkHandoffBridge212A.cleaned(first.name),
            pct,
            computeDelta(first.movement, invert: false),
            false
        )
    }

    /// Builds 3 real pairs strictly following Fable's approved pick rule:
    /// each pick is 1 game (within 24h, league priority NFL > NBA > MLB > NHL > NCAAF > NCAAB > top soccer)
    /// paired with 1 non-sports card from Discover's top-down order, all 5...95%, zero grim topics.
    static func buildPairs(
        from feedItems: [FeedItem],
        arrivedHeadline: String? = nil,
        now: Date = Date()
    ) -> [FirstRunPair212A] {
        let games = extractGameCards(from: feedItems, now: now)
        let nonSports = extractNonSportsCards(from: feedItems, now: now)

        guard games.count >= 3, nonSports.count >= 3 else {
            return []
        }

        let cleanArrived = FirstRunLinkHandoffBridge212A.cleaned(arrivedHeadline)
        let pill = cleanArrived.map { FirstRunLinkHandoffBridge212A.bannerText(headline: $0) }

        return [
            FirstRunPair212A(
                id: "pair-1",
                promptTitle: "Which of these would you check?",
                arrivedContextPill: pill,
                topCard: withWorkedMeaning(games[0]),
                bottomCard: nonSports[0]
            ),
            FirstRunPair212A(
                id: "pair-2",
                promptTitle: "How about these two?",
                arrivedContextPill: nil,
                topCard: games[1],
                bottomCard: nonSports[1]
            ),
            FirstRunPair212A(
                id: "pair-3",
                promptTitle: "And between these two?",
                arrivedContextPill: nil,
                topCard: games[2],
                bottomCard: nonSports[2]
            ),
        ]
    }

    private static func withWorkedMeaning(_ card: FirstRunCard212A) -> FirstRunCard212A {
        FirstRunCard212A(
            id: card.id,
            kicker: card.kicker,
            subtitleRight: card.subtitleRight,
            title: card.title,
            detailLine: card.detailLine,
            percent: card.percent,
            percentLabel: card.percentLabel,
            deltaPoints: card.deltaPoints,
            accentHex: card.accentHex,
            sfSymbol: card.sfSymbol,
            logoUrl: card.logoUrl,
            isSports: card.isSports,
            affinityCategory: card.affinityCategory,
            workedMeaningLine: card.workedMeaningLine ?? FirstRunCard212A.workedMeaning(percent: card.percent),
            followedSubject: card.followedSubject,
            marketId: card.marketId,
            matchKeywords: card.matchKeywords
        )
    }

    private static let isoWithFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoStandard: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static func parseCommenceDate(_ raw: String?) -> Date? {
        guard let s = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else {
            return nil
        }
        return isoWithFractional.date(from: s) ?? isoStandard.date(from: s)
    }

    static func classifyFuturesCategory(_ fut: FeedFuturesData) -> (isSports: Bool, isUnambiguous: Bool, categoryKey: String) {
        let rawCat = (fut.llmSportCategory ?? fut.sport ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let sportTok = fut.sport.map { DiscoverCategory.token(forSport: $0) }
        if let sport = fut.sport, !sport.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            let key = (sportTok == "other" || sportTok == nil) ? (rawCat.isEmpty ? "sports" : rawCat) : sportTok!
            return (true, true, key)
        }
        if explicitlySportsCategories.contains(rawCat) {
            return (true, true, rawCat)
        }
        if let tok = sportTok, explicitlySportsCategories.contains(tok) {
            return (true, true, tok)
        }
        if explicitlyNonSportsCategories.contains(rawCat) {
            return (false, true, rawCat)
        }
        for token in explicitlyNonSportsCategories where rawCat.contains(token) {
            return (false, true, rawCat)
        }
        for token in explicitlySportsCategories where rawCat.contains(token) {
            return (true, true, rawCat)
        }
        return (false, false, rawCat.isEmpty ? "other" : rawCat)
    }

    private static func resolvedPercent(rawProb: Double?, servedRenderedPercent: Int?) -> Int? {
        if let rendered = servedRenderedPercent, (1...99).contains(rendered) {
            return rendered
        }
        guard let prob = rawProb, prob.isFinite else { return nil }
        let scaled = prob > 1.0 && prob <= 100.0 ? prob : prob * 100.0
        let pct = Int(scaled.rounded())
        guard (1...99).contains(pct) else { return nil }
        return pct
    }

    private static func normalizedDelta(prob: Double?, prev: Double?) -> Int? {
        guard let prob, let prev, prob.isFinite, prev.isFinite else { return nil }
        let pNow = prob > 1.0 ? prob / 100.0 : prob
        let pPrev = prev > 1.0 ? prev / 100.0 : prev
        let diff = Int(((pNow - pPrev) * 100.0).rounded())
        return diff == 0 ? nil : diff
    }

    private static func extractGameCards(from rawItems: [FeedItem], now: Date) -> [FirstRunCard212A] {
        var ranked: [(prio: Int, seq: Int, card: FirstRunCard212A)] = []
        var seenIds: Set<String> = []
        var seq = 0

        let earliestStart = now.addingTimeInterval(-4 * 3600)
        let latestStart = now.addingTimeInterval(24 * 3600)

        func considerEvent(_ ev: FeedEventData) {
            defer { seq += 1 }
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { return }
            guard let prio = leaguePriority(for: ev.sport) else { return }
            guard let start = parseCommenceDate(ev.commenceTime),
                  start >= earliestStart, start <= latestStart else {
                return
            }
            let prob = ev.currentOdds?.homeProbability ?? ev.openingOdds?.homeProbability
            guard let pct = resolvedPercent(rawProb: prob, servedRenderedPercent: ev.currentOdds?.homeRenderedPercent),
                  (5...95).contains(pct) else {
                return
            }
            let cardId = "ev-\(ev.id)"
            guard seenIds.insert(cardId).inserted else { return }

            let cat = DiscoverCategory.token(forSport: ev.sport)
            let leagueLabel = sportDisplayName(for: ev.sport)
            let shortNames = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
            let sportTag = leagueLabel.isEmpty ? "Sports" : leagueLabel
            let subject = FollowedSubject295A.teamFromEventSide(event: ev, isHome: true)
            let deltaPts = normalizedDelta(prob: prob, prev: ev.prematchOdds?.homeProbability ?? ev.openingOdds?.homeProbability)

            var detail: String?
            if let proj = ev.pregameProjection,
               let awayProj = proj.projectedAwayScore,
               let homeProj = proj.projectedHomeScore {
                detail = "Projected: \(shortNames.away) \(Int(awayProj.rounded())) \u{2013} \(shortNames.home) \(Int(homeProj.rounded()))"
            }

            let card = FirstRunCard212A(
                id: cardId,
                kicker: sportTag.uppercased(),
                subtitleRight: statusLower == "live" ? "Live now" : nil,
                title: "\(shortNames.away) at \(shortNames.home)",
                detailLine: detail,
                percent: pct,
                percentLabel: shortNames.home,
                deltaPoints: deltaPts,
                accentHex: ev.homeTeamData?.primaryColor ?? "#047857",
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: cat, isSports: true),
                logoUrl: ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge,
                isSports: true,
                affinityCategory: cat,
                workedMeaningLine: nil,
                followedSubject: subject,
                marketId: nil,
                matchKeywords: [shortNames.away, shortNames.home, ev.homeTeam, ev.awayTeam]
            )
            ranked.append((prio, seq, card))
        }

        for item in rawItems {
            if let ev = item.event {
                considerEvent(ev)
            } else if let bundle = item.bundle {
                for child in bundle.items {
                    if let ev = child.event {
                        considerEvent(ev)
                    }
                }
            }
        }

        ranked.sort { lhs, rhs in
            if lhs.prio != rhs.prio { return lhs.prio < rhs.prio }
            return lhs.seq < rhs.seq
        }
        return Array(ranked.prefix(6).map(\.card))
    }

    private static func extractNonSportsCards(from rawItems: [FeedItem], now: Date) -> [FirstRunCard212A] {
        var candidates: [FirstRunCard212A] = []
        var seenIds: Set<String> = []

        func makeCard(fut: FeedFuturesData, collectionRef: FeedThemeCollectionRef?) -> FirstRunCard212A? {
            guard !FeedLifecycle.futuresIsSettled(fut, now: now) else { return nil }
            let mTypeLower = (fut.marketType ?? "").lowercased()
            if mTypeLower == "threshold" || mTypeLower == "quantity" || mTypeLower == "date" {
                return nil
            }
            let classification = classifyFuturesCategory(fut)
            guard classification.isUnambiguous, !classification.isSports else { return nil }
            guard let resolved = resolvePrimaryOutcome(for: fut),
                  (5...95).contains(resolved.percent) else {
                return nil
            }
            guard !isGrimOrSensitiveTopic(title: fut.name, outcomeName: resolved.outcomeName) else {
                return nil
            }
            let cardId = "fut-\(fut.id)"
            guard seenIds.insert(cardId).inserted else { return nil }

            let catKey = classification.categoryKey
            let servedHook = FirstRunLinkHandoffBridge212A.cleaned(fut.hookDescription)
            let followedSet: FollowedSubject295A? = collectionRef.map {
                FollowedSubject295A.set(slug: $0.slug, setKind: .container, name: $0.name)
            }

            return FirstRunCard212A(
                id: cardId,
                kicker: trustedNonSportsPill(categoryKey: catKey, title: fut.name),
                subtitleRight: resolved.outcomeName,
                title: fut.name,
                detailLine: servedHook,
                percent: resolved.percent,
                percentLabel: "chance",
                deltaPoints: resolved.deltaPoints,
                accentHex: "#7C3AED",
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: catKey, isSports: false),
                logoUrl: FirstRunLinkHandoffBridge212A.cleaned(fut.imageUrl),
                isSports: false,
                affinityCategory: catKey,
                workedMeaningLine: nil,
                followedSubject: followedSet,
                marketId: fut.id,
                matchKeywords: [fut.name, resolved.outcomeName ?? "", catKey].filter { !$0.isEmpty }
            )
        }

        // Preserve exact Discover top-down order, taking at most one card per bundle.
        for item in rawItems {
            if let fut = item.futures {
                if let card = makeCard(fut: fut, collectionRef: nil) {
                    candidates.append(card)
                }
            } else if let bundle = item.bundle {
                for child in bundle.items {
                    if let fut = child.futures,
                       let card = makeCard(fut: fut, collectionRef: bundle.collectionRef) {
                        candidates.append(card)
                        break
                    }
                }
            }
        }

        var selected: [FirstRunCard212A] = []
        var usedCategories: Set<String> = []
        for card in candidates {
            if usedCategories.insert(card.affinityCategory).inserted {
                selected.append(card)
            }
            if selected.count >= 3 { return selected }
        }
        for card in candidates where !selected.contains(where: { $0.id == card.id }) {
            selected.append(card)
            if selected.count >= 3 { break }
        }
        return selected
    }
}

/// One live example prompt displayed under Screen 2D's search box (Alex Point 8).
nonisolated struct FirstRunExamplePrompt212A: Identifiable, Equatable, Sendable {
    enum Kind: String, Equatable, Sendable {
        case city
        case school
        case subject
    }

    let id: String
    let kind: Kind
    let query: String
    let displayText: String
}

/// Extracts quiet example prompts strictly from real live served payloads (never hardcoded in app).
nonisolated enum FirstRunServedExamples212A {
    private static let ncaaSportPrefixes = ["basketball_ncaab", "basketball_wncaab", "americanfootball_ncaaf"]
    private static let collegeIndicators: Set<String> = [
        "Wolverines", "Spartans", "Buckeyes", "Bears", "Wildcats", "Tar Heels",
        "Blue Devils", "Gators", "Tigers", "Huskies", "Cougars", "Bulldogs",
        "Beavers", "Wolf Pack", "Owls", "Jaguars", "Panthers", "Antelopes",
        "Hurricane", "Rebels", "Bruins", "Thunderbirds", "Red Wolves", "Salukis",
        "Blue Raiders", "Tribe", "Longhorns", "Crimson Tide", "Fighting Irish",
        "Hoosiers", "Terriers", "Eagles",
    ]
    private static let proMascotWords: Set<String> = [
        "Bruins", "Celtics", "Red Sox", "Patriots", "Revolution", "76ers", "Sixers",
        "Eagles", "Flyers", "Phillies", "Trail Blazers", "Timberwolves", "Nets",
        "Lakers", "Clippers", "Dodgers", "Kings", "Mammoth", "Jets", "Grizzlies",
        "Hornets", "Suns", "Pelicans", "Canadiens", "Knicks", "Rangers", "Islanders",
        "Giants", "Yankees", "Mets", "Warriors", "Bulls", "Cubs", "Bears",
        "Blackhawks", "Heat", "Dolphins", "Inter Miami", "Panthers", "Chiefs",
        "Royals", "Ravens", "Orioles", "Packers", "Brewers", "Bills", "Sabres",
    ]

    static func buildExamples(
        from feedItems: [FeedItem],
        searchSuggestions: [SearchSuggestionEntry212A] = []
    ) -> [FirstRunExamplePrompt212A] {
        var cityExample: FirstRunExamplePrompt212A?
        var schoolExample: FirstRunExamplePrompt212A?
        var subjectExamples: [FirstRunExamplePrompt212A] = []
        var seenQueries: Set<String> = []

        func appendSubject(query: String, display: String) {
            let cleanQ = query.trimmingCharacters(in: .whitespacesAndNewlines)
            let cleanD = display.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !cleanQ.isEmpty, seenQueries.insert(cleanQ.lowercased()).inserted else { return }
            subjectExamples.append(
                FirstRunExamplePrompt212A(id: "subject:\(cleanQ.lowercased())", kind: .subject, query: cleanQ, displayText: cleanD)
            )
        }

        // Flatten items once
        var flat: [(FeedItem, FeedBundle?)] = []
        for item in feedItems {
            if let bundle = item.bundle {
                for child in bundle.items { flat.append((child, bundle)) }
            } else {
                flat.append((item, nil))
            }
        }

        // 1. Live city from pro teams (events or pro futures) & live school from college teams
        for (item, _) in flat {
            if let ev = item.event {
                let sport = (ev.sport ?? "").lowercased()
                let isNCAA = ncaaSportPrefixes.contains { sport.hasPrefix($0) }
                if isNCAA {
                    if schoolExample == nil,
                       let school = extractSchoolName(from: ev.awayTeam) ?? extractSchoolName(from: ev.homeTeam),
                       seenQueries.insert(school.lowercased()).inserted {
                        schoolExample = FirstRunExamplePrompt212A(id: "school:\(school.lowercased())", kind: .school, query: school, displayText: school)
                    }
                } else {
                    if cityExample == nil,
                       let city = extractCityName(location: nil, teamName: ev.homeTeam)
                        ?? extractCityName(location: nil, teamName: ev.awayTeam),
                       seenQueries.insert(city.lowercased()).inserted {
                        cityExample = FirstRunExamplePrompt212A(id: "city:\(city.lowercased())", kind: .city, query: city, displayText: city)
                    }
                }
            } else if let fut = item.futures {
                let cls = FirstRunPair212A.classifyFuturesCategory(fut)
                if cls.isSports, cityExample == nil {
                    if let city = extractCityMention(in: fut.name), seenQueries.insert(city.lowercased()).inserted {
                        cityExample = FirstRunExamplePrompt212A(id: "city:\(city.lowercased())", kind: .city, query: city, displayText: city)
                    }
                }
            }
        }

        if schoolExample == nil {
            for sug in searchSuggestions where sug.type == "event" {
                if let school = extractSchoolName(from: sug.query), seenQueries.insert(school.lowercased()).inserted {
                    schoolExample = FirstRunExamplePrompt212A(id: "school:\(school.lowercased())", kind: .school, query: school, displayText: school)
                    break
                }
            }
        }

        // 2. Non-sports subjects strictly from live non-sports bundles/futures
        for (item, parentBundle) in flat {
            guard let fut = item.futures else { continue }
            let cls = FirstRunPair212A.classifyFuturesCategory(fut)
            guard cls.isUnambiguous && !cls.isSports else { continue }
            guard !FeedLifecycle.futuresIsSettled(fut) else { continue }
            if let deriv = deriveSubjectQueryAndDisplay(future: fut, bundleTitle: parentBundle?.title, categoryKey: cls.categoryKey) {
                appendSubject(query: deriv.query, display: deriv.display)
            }
            if subjectExamples.count >= 4 { break }
        }

        var ordered: [FirstRunExamplePrompt212A] = []
        if let cityExample { ordered.append(cityExample) }
        if let schoolExample { ordered.append(schoolExample) }
        ordered.append(contentsOf: subjectExamples)
        return Array(ordered.prefix(5))
    }

    private static func deriveSubjectQueryAndDisplay(
        future: FeedFuturesData,
        bundleTitle: String?,
        categoryKey: String
    ) -> (query: String, display: String)? {
        let lowerName = future.name.lowercased()
        let bundleLower = (bundleTitle ?? "").lowercased()
        if lowerName.contains("oscar") || bundleLower.contains("oscar") {
            return ("Oscars", "Oscars")
        }
        if lowerName.contains("inflation") || bundleLower.contains("inflation") {
            return ("inflation", "Inflation")
        }
        if lowerName.contains("fed") || bundleLower.contains("fed") || lowerName.contains("rate") {
            return ("inflation", "Inflation")
        }
        if categoryKey == "entertainment" && (lowerName.contains("bond") || lowerName.contains("spotify") || lowerName.contains("album") || lowerName.contains("movie")) {
            return ("Oscars", "Oscars")
        }
        if categoryKey == "economics" {
            return ("inflation", "Inflation")
        }
        if categoryKey == "weather" || lowerName.contains("rain") || lowerName.contains("snow") || lowerName.contains("temp") {
            return ("weather", "Weather")
        }
        if categoryKey == "tech" || lowerName.contains("ai") || lowerName.contains("openai") {
            return ("AI", "AI")
        }
        if categoryKey == "politics" || categoryKey == "geopolitics" {
            return ("elections", "Elections")
        }
        return nil
    }

    private static func extractSchoolName(from rawTeam: String) -> String? {
        let trimmed = rawTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let matchedMascot = collegeIndicators.first { trimmed.hasSuffix(" \($0)") }
        guard let mascot = matchedMascot else { return nil }
        var school = String(trimmed.dropLast(mascot.count + 1)).trimmingCharacters(in: .whitespacesAndNewlines)
        if school.hasSuffix(" St") {
            school = String(school.dropLast(3)) + " State"
        }
        return school.isEmpty ? nil : school
    }

    private static func extractCityName(location: String?, teamName: String) -> String? {
        if let loc = location?.trimmingCharacters(in: .whitespacesAndNewlines), !loc.isEmpty {
            return loc
        }
        let trimmed = teamName.trimmingCharacters(in: .whitespacesAndNewlines)
        for mascot in proMascotWords where trimmed.hasSuffix(" \(mascot)") {
            let prefix = String(trimmed.dropLast(mascot.count + 1)).trimmingCharacters(in: .whitespacesAndNewlines)
            if !prefix.isEmpty {
                return prefix
            }
        }
        return nil
    }

    private static func extractCityMention(in title: String) -> String? {
        let knownProPrefixes = [
            "Boston", "New York", "Los Angeles", "Chicago", "Philadelphia", "Denver",
            "Seattle", "Miami", "Detroit", "Houston", "Atlanta", "Phoenix", "Dallas",
        ]
        for city in knownProPrefixes where title.localizedCaseInsensitiveContains(city) {
            return city
        }
        return nil
    }
}

/// One unified item in Screen 2D (`"Any cities, schools or subjects you care about?"`).
nonisolated struct FirstRunSuggestion212A: Identifiable, Equatable, Sendable {
    let id: String
    let name: String
    let sportOrCategoryLabel: String
    let contextLine: String?
    let logoUrl: String?
    let primaryColorHex: String?
    let teamId: Int?
    let sportKey: String?
    let followedSubject: FollowedSubject295A?
    let affinityCategory: String?
    let marketId: Int?
    let matchKeywords: [String]

    var chipDisplayText: String {
        if !sportOrCategoryLabel.isEmpty, sportOrCategoryLabel != "Set" {
            return "\(name) \u{00B7} \(sportOrCategoryLabel)"
        }
        return name
    }

    var rowSubtitleText: String {
        switch (sportOrCategoryLabel.isEmpty ? nil : sportOrCategoryLabel, contextLine?.isEmpty == false ? contextLine : nil) {
        case let (sport?, ctx?):
            return "\(sport) \u{00B7} \(ctx)"
        case let (sport?, nil):
            return sport
        case let (nil, ctx?):
            return ctx
        case (nil, nil):
            return "Subject"
        }
    }

    private static func plainSubjectKind(label: String, rawCategory: String) -> String {
        let lowerLabel = label.lowercased()
        let lowerCat = rawCategory.lowercased()
        if lowerLabel.contains("oscar") || lowerLabel.contains("grammy") || lowerLabel.contains("emmy")
            || lowerLabel.contains("tony") || lowerLabel.contains("golden globe") || lowerLabel.contains("bafta")
            || lowerCat == "awards" {
            return "Awards"
        }
        if lowerCat.contains("econ") || lowerCat == "macro" || lowerCat == "finance"
            || lowerLabel.contains("inflation") || lowerLabel.contains("fed") || lowerLabel.contains("rate") {
            return "Economy"
        }
        if lowerCat == "entertainment" || lowerCat == "culture" || lowerCat == "movies" || lowerCat == "film"
            || lowerCat == "music" || lowerCat == "tv" {
            return "Entertainment"
        }
        if lowerCat == "tech" || lowerCat == "ai" || lowerCat == "science" {
            return "Tech"
        }
        if lowerCat.contains("politic") || lowerCat.contains("election") || lowerCat.contains("geopolitic") {
            return "Politics"
        }
        if lowerCat == "weather" || lowerCat == "climate" {
            return "Weather"
        }
        return "Subject"
    }

    /// Expands `/api/me/teams/*` responses into distinct per-(team, sport) suggestions.
    static func fromTeamSearchResults(
        _ results: [TeamSearchResult],
        contextHint: String? = nil
    ) -> [FirstRunSuggestion212A] {
        var out: [FirstRunSuggestion212A] = []
        var seenTeamIds: Set<Int> = []
        for result in results {
            let variants = (result.sports ?? []).filter { !($0.sportKey ?? "").isEmpty }
            if variants.count > 1 {
                for variant in variants {
                    guard seenTeamIds.insert(variant.id).inserted else { continue }
                    let label = nonEmpty(variant.sportDisplay) ?? sportDisplayName(for: variant.sportKey)
                    let resolvedLabel = label.isEmpty ? "Team" : label
                    out.append(FirstRunSuggestion212A(
                        id: "team:\(variant.id)",
                        name: result.name,
                        sportOrCategoryLabel: resolvedLabel,
                        contextLine: contextHint ?? result.location,
                        logoUrl: result.logoUrl,
                        primaryColorHex: nil,
                        teamId: variant.id,
                        sportKey: variant.sportKey,
                        followedSubject: FollowedSubject295A.team(
                            slug: "\(variant.id)",
                            teamId: variant.id,
                            name: result.name,
                            sportKey: variant.sportKey,
                            logoUrl: result.logoUrl
                        ),
                        affinityCategory: DiscoverCategory.token(forSport: variant.sportKey),
                        marketId: nil,
                        matchKeywords: [result.name, result.location ?? ""].filter { !$0.isEmpty }
                    ))
                }
            } else {
                guard seenTeamIds.insert(result.id).inserted else { continue }
                let key = result.sportKey ?? result.sports?.first?.sportKey
                let rawDisplay = nonEmpty(result.sports?.first?.sportDisplay) ?? sportDisplayName(for: key)
                let resolvedLabel = rawDisplay.isEmpty ? "Team" : rawDisplay
                out.append(FirstRunSuggestion212A(
                    id: "team:\(result.id)",
                    name: result.name,
                    sportOrCategoryLabel: resolvedLabel,
                    contextLine: contextHint ?? result.location,
                    logoUrl: result.logoUrl,
                    primaryColorHex: nil,
                    teamId: result.id,
                    sportKey: key,
                    followedSubject: FollowedSubject295A.team(
                        slug: "\(result.id)",
                        teamId: result.id,
                        name: result.name,
                        sportKey: key,
                        logoUrl: result.logoUrl
                    ),
                    affinityCategory: DiscoverCategory.token(forSport: key),
                    marketId: nil,
                    matchKeywords: [result.name, result.location ?? ""].filter { !$0.isEmpty }
                ))
            }
        }
        return out
    }

    /// Expands `/api/events/search` strictly into teams, schools, cities, and subjects ONLY
    /// (Fable Send-back 4: zero rows of kind `"Set"` and zero single forecasts).
    static func fromEventSearchResponse(
        _ response: SearchResponse,
        query: String
    ) -> [FirstRunSuggestion212A] {
        var out: [FirstRunSuggestion212A] = []
        let trimmedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowerQuery = trimmedQuery.lowercased()
        let teamNames = (response.teams ?? []).map(\.name)

        // 1. Teams
        for team in response.teams ?? [] {
            let label = sportDisplayName(for: team.sportKey)
            let resolvedLabel = label.isEmpty ? "Team" : label
            out.append(FirstRunSuggestion212A(
                id: "team:\(team.id)",
                name: team.name,
                sportOrCategoryLabel: resolvedLabel,
                contextLine: nonEmpty(team.record),
                logoUrl: team.logo,
                primaryColorHex: nil,
                teamId: team.id,
                sportKey: team.sportKey,
                followedSubject: FollowedSubject295A.team(
                    slug: nonEmpty(team.slug) ?? "\(team.id)",
                    teamId: team.id,
                    name: team.name,
                    sportKey: team.sportKey,
                    logoUrl: team.logo,
                    primaryColor: nil
                ),
                affinityCategory: DiscoverCategory.token(forSport: team.sportKey),
                marketId: nil,
                matchKeywords: [team.name, team.abbreviation ?? ""].filter { !$0.isEmpty }
            ))
        }

        // 2. Real served topical subjects (`Oscars`, `Fed & Rates`, `Inflation`, etc.)
        // Never emit `"Set"`, single forecasts, or person/election collisions for unrelated team queries.
        let sportsShortKeys: Set<String> = ["basketball", "football", "baseball", "hockey", "soccer", "tennis", "golf"]
        for family in (response.futuresFamilies ?? []).prefix(5) {
            let rawCat = (family.headline.llmSportCategory ?? family.headline.category ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let labelMatchesQuery = trimmedQuery.isEmpty
                || family.label.localizedCaseInsensitiveContains(trimmedQuery)
                || trimmedQuery.localizedCaseInsensitiveContains(family.label)
                || family.familyKey.localizedCaseInsensitiveContains(trimmedQuery)
                || (family.familyKey == "story:macro_rates" && (lowerQuery.contains("inflation") || lowerQuery.contains("fed") || lowerQuery.contains("rate")))
            guard labelMatchesQuery else { continue }

            if family.familyKey.hasPrefix("entity:") {
                let isSportsCat = FirstRunPair212A.explicitlySportsCategories.contains(rawCat) || sportsShortKeys.contains(rawCat)
                let matchesReturnedTeam = teamNames.contains { $0.localizedCaseInsensitiveContains(family.label) }
                if isSportsCat || matchesReturnedTeam {
                    continue
                }
            }

            let kindLabel = plainSubjectKind(label: family.label, rawCategory: rawCat)
            let category = rawCat.isEmpty ? nil : rawCat
            out.append(FirstRunSuggestion212A(
                id: "family:\(family.familyKey)",
                name: family.label,
                sportOrCategoryLabel: kindLabel,
                contextLine: nil,
                logoUrl: nil,
                primaryColorHex: rawCat.contains("econ") ? "#005CC2" : "#B45309",
                teamId: nil,
                sportKey: category,
                followedSubject: FollowedSubject295A.subject(
                    slug: family.familyKey,
                    name: family.label,
                    affinityCategory: category,
                    marketId: family.headline.id,
                    primaryColor: rawCat.contains("econ") ? "#005CC2" : "#B45309",
                    searchQuery: family.label
                ),
                affinityCategory: category,
                marketId: family.headline.id,
                matchKeywords: [family.label, trimmedQuery].filter { !$0.isEmpty }
            ))
        }

        return mergeDeduplicating(out)
    }

    static func mergeDeduplicating(_ lists: [FirstRunSuggestion212A]) -> [FirstRunSuggestion212A] {
        var seen: Set<String> = []
        var out: [FirstRunSuggestion212A] = []
        for item in lists {
            if seen.insert(item.id).inserted {
                out.append(item)
            }
        }
        return out
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }
}

/// First-run persistent state keys shared across Step 1, Step 2, Step 5, and launch deferral.
nonisolated enum FirstRunStorageKeys212A {
    static let onboardedKey = "discover_onboarded"
    static let localInterestsKey = "bainluck_first_run_interests_212a"
    static let localPreferencesKey = "bainluck_first_run_prefs_v2_212a"
    static let earnedSignInDismissedKey = "bainluck_earned_signin_dismissed_212a"
}

/// Persisted first-run picks read immediately by `DiscoverView` on the next screen
/// (Fable Point 3 & Alex Point 9).
nonisolated struct FirstRunPreferences212A: Codable, Equatable, Sendable {
    /// Ruling 405: A — first-run picks boost matching cards for one week, then stop.
    static let boostDurationSeconds: TimeInterval = 7 * 24 * 60 * 60

    var boostedCategories: [String]
    var boostedTerms: [String]
    var boostedMarketIds: [Int]
    var savedAtEpoch: TimeInterval?

    static let empty = FirstRunPreferences212A(
        boostedCategories: [],
        boostedTerms: [],
        boostedMarketIds: [],
        savedAtEpoch: nil
    )

    init(
        boostedCategories: [String],
        boostedTerms: [String],
        boostedMarketIds: [Int],
        savedAtEpoch: TimeInterval? = nil
    ) {
        self.boostedCategories = boostedCategories
        self.boostedTerms = boostedTerms
        self.boostedMarketIds = boostedMarketIds
        self.savedAtEpoch = savedAtEpoch
    }

    var isEmpty: Bool {
        boostedCategories.isEmpty && boostedTerms.isEmpty && boostedMarketIds.isEmpty
    }

    func isBoostActive(now: Date = Date()) -> Bool {
        guard !isEmpty, let savedAtEpoch else { return false }
        return now.timeIntervalSince1970 < savedAtEpoch + Self.boostDurationSeconds
    }

    static func load(defaults: UserDefaults = .standard) -> FirstRunPreferences212A {
        guard let data = defaults.data(forKey: FirstRunStorageKeys212A.localPreferencesKey),
              let decoded = try? JSONDecoder().decode(FirstRunPreferences212A.self, from: data) else {
            return .empty
        }
        return decoded
    }

    func save(defaults: UserDefaults = .standard, now: Date = Date()) {
        var payload = self
        if !payload.isEmpty, payload.savedAtEpoch == nil {
            payload.savedAtEpoch = now.timeIntervalSince1970
        }
        if let data = try? JSONEncoder().encode(payload) {
            defaults.set(data, forKey: FirstRunStorageKeys212A.localPreferencesKey)
        }
    }

    /// Plain-English confirmation line on Screen 2D after the pairs (Fable Point 3):
    /// e.g. `"More awards and economy in your Discover."`
    static func changeSummaryLine(from pickedCards: [FirstRunCard212A]) -> String? {
        guard !pickedCards.isEmpty else { return nil }
        var labels: [String] = []
        for card in pickedCards {
            let label = summaryNoun(forCategory: card.affinityCategory, title: card.title)
            if !labels.contains(label) {
                labels.append(label)
            }
            if labels.count >= 3 { break }
        }
        guard !labels.isEmpty else { return nil }
        let joined: String
        switch labels.count {
        case 1:
            joined = labels[0]
        case 2:
            joined = "\(labels[0]) and \(labels[1])"
        default:
            joined = "\(labels[0]), \(labels[1]), and \(labels[2])"
        }
        return "More \(joined) in your Discover."
    }

    static func summaryNoun(forCategory category: String, title: String) -> String {
        let lower = category.lowercased()
        let titleLower = title.lowercased()
        if titleLower.contains("oscar") || lower == "awards" { return "awards" }
        if lower == "entertainment" || lower == "culture" || lower == "movies" || lower == "music" {
            return "entertainment"
        }
        if lower == "economics" || lower == "econ" || lower == "macro" || lower == "finance" {
            return "economy"
        }
        if lower == "tech" || lower == "ai" || lower == "science" {
            return "tech & AI"
        }
        if lower == "weather" || lower == "climate" {
            return "weather"
        }
        if lower == "politics" || lower == "geopolitics" {
            return "politics"
        }
        if lower == "americanfootball" || lower == "nfl" || lower == "football" { return "football" }
        if lower == "basketball" || lower == "nba" || lower == "ncaab" || lower == "wncaab" { return "basketball" }
        if lower == "baseball" || lower == "mlb" { return "baseball" }
        if lower == "icehockey" || lower == "hockey" || lower == "nhl" { return "hockey" }
        if lower == "soccer" { return "soccer" }
        if lower == "tennis" { return "tennis" }
        if lower == "golf" { return "golf" }
        return category.lowercased()
    }
}

/// Promotes up to three cards per picked kind into the first ten Discover seats for
/// one week from saving without ever removing or inventing items (#11984 / 405: A).
nonisolated enum FirstRunDiscoverBoost212A {
    static let openingWindowSize = 10
    static let maxPromotedPerKind = 3

    static func promotePreferredItems<Item>(
        _ items: [Item],
        preferences: FirstRunPreferences212A,
        now: Date = Date(),
        windowSize: Int = FirstRunDiscoverBoost212A.openingWindowSize,
        maxPerKind: Int = FirstRunDiscoverBoost212A.maxPromotedPerKind,
        kindOf: (Item) -> String = { _ in "picked" },
        matches: (Item, FirstRunPreferences212A) -> Bool
    ) -> [Item] {
        guard preferences.isBoostActive(now: now), items.count > 1, windowSize > 0, maxPerKind > 0 else {
            return items
        }

        let windowLimit = min(windowSize, items.count)
        var promoted: [Item] = []
        var rest: [Item] = []
        var promotedByKind: [String: Int] = [:]
        promoted.reserveCapacity(windowLimit)
        rest.reserveCapacity(items.count)

        for item in items {
            if matches(item, preferences) {
                let kind = kindOf(item)
                if promoted.count < windowLimit, promotedByKind[kind, default: 0] < maxPerKind {
                    promoted.append(item)
                    promotedByKind[kind, default: 0] += 1
                    continue
                }
            }
            rest.append(item)
        }

        var firstWindow = promoted
        var windowKindCounts = promotedByKind
        var deferredMatches: [Item] = []
        var tail: [Item] = []

        for item in rest {
            if firstWindow.count < windowLimit {
                if matches(item, preferences) {
                    let kind = kindOf(item)
                    if windowKindCounts[kind, default: 0] >= maxPerKind {
                        deferredMatches.append(item)
                        continue
                    }
                    windowKindCounts[kind, default: 0] += 1
                }
                firstWindow.append(item)
            } else {
                tail.append(item)
            }
        }

        var deferredIndex = 0
        while firstWindow.count < windowLimit, deferredIndex < deferredMatches.count {
            firstWindow.append(deferredMatches[deferredIndex])
            deferredIndex += 1
        }

        let remainingDeferred = deferredIndex < deferredMatches.count
            ? Array(deferredMatches[deferredIndex...])
            : []
        return firstWindow + remainingDeferred + tail
    }

    static func itemMatches(
        _ item: FeedItem,
        category: String,
        preferences: FirstRunPreferences212A
    ) -> Bool {
        let catLower = category.lowercased()
        let normalizedPrefsCats = Set(preferences.boostedCategories.map { $0.lowercased() })
        if normalizedPrefsCats.contains(catLower) {
            return true
        }
        for prefCat in normalizedPrefsCats {
            if categoryGroup(prefCat) == categoryGroup(catLower), categoryGroup(prefCat) != "other" {
                return true
            }
        }

        let marketIds = Set(preferences.boostedMarketIds)
        if let fut = item.futures, marketIds.contains(fut.id) { return true }
        if let bundle = item.bundle {
            for child in bundle.items {
                if let fut = child.futures, marketIds.contains(fut.id) { return true }
            }
        }

        let terms = preferences.boostedTerms.map { $0.lowercased() }.filter { $0.count >= 3 }
        guard !terms.isEmpty else { return false }
        let haystack = searchText(for: item)
        return terms.contains { haystack.contains($0) }
    }

    static func categoryGroup(_ raw: String) -> String {
        switch raw {
        case "nba", "basketball", "ncaab", "wncaab": return "basketball"
        case "nfl", "americanfootball", "ncaaf", "football": return "football"
        case "mlb", "baseball": return "baseball"
        case "nhl", "icehockey", "hockey": return "hockey"
        case "entertainment", "awards", "culture", "movies", "music": return "entertainment"
        case "economics", "econ", "macro", "finance": return "economics"
        case "tech", "ai", "science": return "tech"
        case "weather", "climate": return "weather"
        case "politics", "geopolitics": return "politics"
        default: return raw.isEmpty ? "other" : raw
        }
    }

    private static func searchText(for item: FeedItem) -> String {
        var parts: [String] = []
        if let ev = item.event {
            parts.append(ev.homeTeam)
            parts.append(ev.awayTeam)
        }
        if let fut = item.futures {
            parts.append(fut.name)
            for out in fut.topOutcomes ?? [] { parts.append(out.name) }
        }
        if let bundle = item.bundle {
            parts.append(bundle.title)
            for child in bundle.items {
                if let fut = child.futures {
                    parts.append(fut.name)
                    for out in fut.topOutcomes ?? [] { parts.append(out.name) }
                }
            }
        }
        return parts.joined(separator: " ").lowercased()
    }
}
