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
    let kicker: String
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

    /// Builds 3 real pairs mixing sports and non-sports items strictly from live unsettled
    /// `/api/feed` items (`Discover` + `Sports`). Never invents placeholder/fallback cards.
    static func buildPairs(
        from feedItems: [FeedItem],
        arrivedHeadline: String? = nil,
        now: Date = Date()
    ) -> [FirstRunPair212A] {
        let nonSports = extractCards(from: feedItems, wantSports: false, now: now)
        let sports = extractCards(from: feedItems, wantSports: true, now: now)

        guard sports.count >= 2, nonSports.count >= 4 else {
            return []
        }

        let cleanArrived = FirstRunLinkHandoffBridge212A.cleaned(arrivedHeadline)
        let pill = cleanArrived.map { FirstRunLinkHandoffBridge212A.bannerText(headline: $0) }

        return [
            FirstRunPair212A(
                id: "pair-1",
                promptTitle: "Which of these would you check?",
                arrivedContextPill: pill,
                topCard: withWorkedMeaning(sports[0]),
                bottomCard: nonSports[0]
            ),
            FirstRunPair212A(
                id: "pair-2",
                promptTitle: "How about these two?",
                arrivedContextPill: nil,
                topCard: sports[1],
                bottomCard: nonSports[1]
            ),
            FirstRunPair212A(
                id: "pair-3",
                promptTitle: "And between these two?",
                arrivedContextPill: nil,
                topCard: nonSports[2],
                bottomCard: nonSports[3]
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

    private struct FlattenedEntry {
        let item: FeedItem
        let collectionRef: FeedThemeCollectionRef?
    }

    private static func flattenedEntries(from items: [FeedItem]) -> [FlattenedEntry] {
        // Put standalone games/markets first in natural order, taking at most one lead open
        // child per Discover bundle so no single bundle dominates all slots.
        var singles: [FlattenedEntry] = []
        var bundleLeads: [FlattenedEntry] = []
        for item in items {
            if let bundle = item.bundle {
                if let lead = bundle.items.first(where: { $0.futures != nil || $0.event != nil }) {
                    bundleLeads.append(FlattenedEntry(item: lead, collectionRef: bundle.collectionRef))
                }
            } else if item.event != nil {
                singles.insert(FlattenedEntry(item: item, collectionRef: nil), at: 0)
            } else {
                singles.append(FlattenedEntry(item: item, collectionRef: nil))
            }
        }
        return singles + bundleLeads
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

    private static func extractCards(from rawItems: [FeedItem], wantSports: Bool, now: Date) -> [FirstRunCard212A] {
        var candidates: [FirstRunCard212A] = []
        var seenIds: Set<String> = []
        for entry in flattenedEntries(from: rawItems) {
            let item = entry.item
            if let ev = item.event, wantSports {
                let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { continue }
                let prob = ev.currentOdds?.homeProbability ?? ev.openingOdds?.homeProbability
                guard let pct = resolvedPercent(rawProb: prob, servedRenderedPercent: ev.currentOdds?.homeRenderedPercent) else {
                    continue
                }
                let cardId = "ev-\(ev.id)"
                guard seenIds.insert(cardId).inserted else { continue }
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

                candidates.append(FirstRunCard212A(
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
                ))
            } else if let fut = item.futures {
                guard !FeedLifecycle.futuresIsSettled(fut, now: now) else { continue }
                let mTypeLower = (fut.marketType ?? "").lowercased()
                // Threshold / date-ladder buckets can show a different rung on Discover vs /futures/<id>.
                if mTypeLower == "threshold" || mTypeLower == "quantity" || mTypeLower == "date" {
                    continue
                }
                let classification = classifyFuturesCategory(fut)
                guard classification.isUnambiguous, classification.isSports == wantSports else { continue }
                guard let firstOutcome = fut.topOutcomes?.first,
                      let pct = resolvedPercent(rawProb: firstOutcome.probability, servedRenderedPercent: firstOutcome.renderedPercent) else {
                    continue
                }
                let cardId = "fut-\(fut.id)"
                guard seenIds.insert(cardId).inserted else { continue }

                let catKey = classification.categoryKey
                let catDisplay = sportCategoryDisplayName(catKey)
                let deltaPts: Int? = {
                    guard let move = firstOutcome.movement, move.isFinite else { return nil }
                    let scaled = abs(move) <= 1.0 ? move * 100.0 : move
                    let diff = Int(scaled.rounded())
                    return diff == 0 ? nil : diff
                }()
                let servedHook = FirstRunLinkHandoffBridge212A.cleaned(fut.hookDescription)
                let ref = entry.collectionRef
                let followedSet: FollowedSubject295A? = ref.map {
                    FollowedSubject295A.set(slug: $0.slug, setKind: .container, name: $0.name)
                }

                candidates.append(FirstRunCard212A(
                    id: cardId,
                    kicker: catDisplay.uppercased(),
                    subtitleRight: FirstRunLinkHandoffBridge212A.cleaned(firstOutcome.name),
                    title: fut.name,
                    detailLine: servedHook,
                    percent: pct,
                    percentLabel: "chance",
                    deltaPoints: deltaPts,
                    accentHex: wantSports ? "#005CC2" : "#7C3AED",
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: catKey, isSports: wantSports),
                    logoUrl: FirstRunLinkHandoffBridge212A.cleaned(fut.imageUrl),
                    isSports: wantSports,
                    affinityCategory: catKey,
                    workedMeaningLine: nil,
                    followedSubject: followedSet,
                    marketId: fut.id,
                    matchKeywords: [fut.name, firstOutcome.name, catDisplay]
                ))
            }
        }

        // Prefer diverse categories and clear mid-range probabilities first without inventing anything.
        // For sports, prefer live/upcoming games over futures when both exist.
        let ordered = candidates.sorted { lhs, rhs in
            if wantSports {
                let lEv = lhs.id.hasPrefix("ev-")
                let rEv = rhs.id.hasPrefix("ev-")
                if lEv != rEv { return lEv }
            }
            let lMid = (15...85).contains(lhs.percent)
            let rMid = (15...85).contains(rhs.percent)
            if lMid != rMid { return lMid }
            return false
        }

        var selected: [FirstRunCard212A] = []
        var usedCategories: Set<String> = []
        for card in ordered {
            if usedCategories.insert(card.affinityCategory).inserted {
                selected.append(card)
            }
            if selected.count >= 4 { return selected }
        }
        for card in ordered where !selected.contains(where: { $0.id == card.id }) {
            selected.append(card)
            if selected.count >= 4 { break }
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
        ordered.append(contentsOf: subjectExamples.prefix(3))
        return ordered
    }

    private static func deriveSubjectQueryAndDisplay(
        future: FeedFuturesData,
        bundleTitle: String?,
        categoryKey: String
    ) -> (query: String, display: String)? {
        let lowerName = future.name.lowercased()
        let bundleLower = (bundleTitle ?? "").lowercased()
        if lowerName.contains("oscar") || bundleLower.contains("oscar") {
            return ("Oscars", "the Oscars")
        }
        if lowerName.contains("inflation") || bundleLower.contains("inflation") {
            return ("inflation", "inflation")
        }
        if lowerName.contains("fed") || bundleLower.contains("fed") || lowerName.contains("rate") {
            return ("inflation", "inflation & rates")
        }
        if categoryKey == "entertainment" && (lowerName.contains("bond") || lowerName.contains("spotify") || lowerName.contains("album") || lowerName.contains("movie")) {
            return ("Oscars", "the Oscars & film")
        }
        if categoryKey == "economics" {
            return ("inflation", "inflation")
        }
        if categoryKey == "weather" || lowerName.contains("rain") || lowerName.contains("snow") || lowerName.contains("temp") {
            return ("weather", "weather")
        }
        if categoryKey == "tech" || lowerName.contains("ai") || lowerName.contains("openai") {
            return ("AI", "AI & tech")
        }
        if categoryKey == "politics" || categoryKey == "geopolitics" {
            return ("elections", "elections")
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
        if !sportOrCategoryLabel.isEmpty {
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

    /// Expands `/api/events/search` response (`teams`, `collections`, `futuresFamilies`, and live open `futures`).
    /// Never uses hardcoded client topic lists — every non-sports row is served live from the API.
    static func fromEventSearchResponse(
        _ response: SearchResponse,
        query: String
    ) -> [FirstRunSuggestion212A] {
        var out: [FirstRunSuggestion212A] = []

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

        // 2. Real served collections / sets (e.g. Oscars Best Picture / Best Actor)
        if let collections = response.collectionDiscovery?.collections {
            for col in collections.prefix(3) {
                let title = nonEmpty(col.name) ?? col.slug
                let count = col.gameCount + col.questionCount
                let countText = count > 0 ? "\(count) items" : nil
                out.append(FirstRunSuggestion212A(
                    id: "set:\(col.slug)",
                    name: title,
                    sportOrCategoryLabel: "Set",
                    contextLine: countText,
                    logoUrl: nil,
                    primaryColorHex: "#7C3AED",
                    teamId: nil,
                    sportKey: nil,
                    followedSubject: FollowedSubject295A.set(slug: col.slug, setKind: .container, name: title),
                    affinityCategory: nil,
                    marketId: nil,
                    matchKeywords: [title, query].filter { !$0.isEmpty }
                ))
            }
        }

        // 3. Real served topical families (`Oscars`, `Fed & Rates`, `Inflation`, etc.)
        for family in (response.futuresFamilies ?? []).prefix(3) {
            let rawCat = (family.headline.llmSportCategory ?? family.headline.category ?? "").lowercased()
            let catDisplay = rawCat.isEmpty ? "Subject" : sportCategoryDisplayName(rawCat)
            out.append(FirstRunSuggestion212A(
                id: "family:\(family.familyKey)",
                name: family.label,
                sportOrCategoryLabel: catDisplay,
                contextLine: nonEmpty(family.headline.name),
                logoUrl: nil,
                primaryColorHex: rawCat.contains("econ") ? "#005CC2" : "#B45309",
                teamId: nil,
                sportKey: rawCat.isEmpty ? nil : rawCat,
                followedSubject: nil,
                affinityCategory: rawCat.isEmpty ? nil : rawCat,
                marketId: family.headline.id,
                matchKeywords: [family.label, family.headline.name, query].filter { !$0.isEmpty }
            ))
        }

        // 4. Open / unsettled served futures matching query (never settled rows)
        for fut in response.futures where !FeedLifecycle.settledStatuses.contains((fut.status ?? "").lowercased()) {
            let rawCat = (fut.llmSportCategory ?? fut.category ?? fut.sport ?? "").lowercased()
            let catDisplay = rawCat.isEmpty ? "Forecast" : sportCategoryDisplayName(rawCat)
            var context: String?
            if let top = fut.topOutcomes?.first {
                let pct = top.renderedPercent ?? top.probability.map { p in Int((p > 1.0 ? p : p * 100.0).rounded()) }
                if let pct, (1...99).contains(pct) {
                    context = "\(top.name) \(pct)%"
                } else {
                    context = nonEmpty(top.name)
                }
            }
            out.append(FirstRunSuggestion212A(
                id: "fut:\(fut.id)",
                name: fut.name,
                sportOrCategoryLabel: catDisplay,
                contextLine: context,
                logoUrl: nil,
                primaryColorHex: rawCat.contains("econ") ? "#005CC2" : "#7C3AED",
                teamId: nil,
                sportKey: rawCat.isEmpty ? nil : rawCat,
                followedSubject: nil,
                affinityCategory: rawCat.isEmpty ? nil : rawCat,
                marketId: fut.id,
                matchKeywords: [fut.name, fut.topOutcomes?.first?.name ?? "", query].filter { !$0.isEmpty }
            ))
            if out.count >= 12 { break }
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
    var boostedCategories: [String]
    var boostedTerms: [String]
    var boostedMarketIds: [Int]

    static let empty = FirstRunPreferences212A(boostedCategories: [], boostedTerms: [], boostedMarketIds: [])

    var isEmpty: Bool {
        boostedCategories.isEmpty && boostedTerms.isEmpty && boostedMarketIds.isEmpty
    }

    static func load(defaults: UserDefaults = .standard) -> FirstRunPreferences212A {
        guard let data = defaults.data(forKey: FirstRunStorageKeys212A.localPreferencesKey),
              let decoded = try? JSONDecoder().decode(FirstRunPreferences212A.self, from: data) else {
            return .empty
        }
        return decoded
    }

    func save(defaults: UserDefaults = .standard) {
        if let data = try? JSONEncoder().encode(self) {
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

/// Promotes cards matching the reader's first-run picks to the top of Discover immediately
/// without ever removing or inventing items (#11984 / Fable Point 3 / Alex Point 9).
nonisolated enum FirstRunDiscoverBoost212A {
    static func promotePreferredItems<Item>(
        _ items: [Item],
        preferences: FirstRunPreferences212A,
        matches: (Item, FirstRunPreferences212A) -> Bool
    ) -> [Item] {
        guard !preferences.isEmpty, items.count > 1 else { return items }
        var preferred: [Item] = []
        var others: [Item] = []
        preferred.reserveCapacity(items.count)
        others.reserveCapacity(items.count)
        for item in items {
            if matches(item, preferences) {
                preferred.append(item)
            } else {
                others.append(item)
            }
        }
        return preferred + others
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

    private static func categoryGroup(_ raw: String) -> String {
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
