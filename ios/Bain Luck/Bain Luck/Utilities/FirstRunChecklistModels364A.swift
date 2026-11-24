import Foundation

// MARK: - Decision 364: A — Single-Screen Five-Row First-Run Checklist (#11934)
//
// Replaces the paused 212-A three-picks (2A..2C) wizard on the sheet while keeping
// all paused 2A..2C code intact on the branch (Item 5).

nonisolated enum FirstRunChecklistRowID364A: String, CaseIterable, Identifiable, Hashable, Codable, Sendable {
    case lookUp = "look_up"
    case follow = "follow"
    case exploreSets = "explore_sets"
    case syncDevices = "sync_devices"
    case alerts = "alerts"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .lookUp: return "Look anything up"
        case .follow: return "Follow what you care about"
        case .exploreSets: return "See what the world expects"
        case .syncDevices: return "Keep it on all your devices"
        case .alerts: return "Get a heads-up"
        }
    }

    var shortLabel: String {
        switch self {
        case .lookUp: return "Look up"
        case .follow: return "Follow"
        case .exploreSets: return "Sets"
        case .syncDevices: return "Sync"
        case .alerts: return "Alerts"
        }
    }

    var accessibilityIdentifier: String {
        "checklist364A.row.\(rawValue)"
    }
}

/// Interactive checklist progress state for both the opening sheet and the compact
/// top-of-My-Stuff banner (`"\(completedCount) of 5 done"` until finished or dismissed).
nonisolated struct FirstRunChecklistState364A: Equatable, Codable, Sendable {
    var completedRows: Set<FirstRunChecklistRowID364A>
    var selectedSetSlugs: Set<String>
    var followedCount: Int
    var dismissedFromMyStuff: Bool

    static let untouched = FirstRunChecklistState364A(
        completedRows: [],
        selectedSetSlugs: [],
        followedCount: 0,
        dismissedFromMyStuff: false
    )

    static let allDone = FirstRunChecklistState364A(
        completedRows: Set(FirstRunChecklistRowID364A.allCases),
        selectedSetSlugs: ["machinery-oscars-best-picture"],
        followedCount: 2,
        dismissedFromMyStuff: false
    )

    var completedCount: Int {
        completedRows.count
    }

    var totalCount: Int {
        FirstRunChecklistRowID364A.allCases.count
    }

    var savedCount: Int {
        followedCount + selectedSetSlugs.count
    }

    /// Row 4 (`"Keep it on all your devices"`) lights up once the reader has
    /// followed or picked something, and stays quiet beforehand (`364: A`).
    var isSyncLitUp: Bool {
        followedCount > 0
            || !selectedSetSlugs.isEmpty
            || completedRows.contains(.follow)
            || completedRows.contains(.exploreSets)
            || completedRows.contains(.syncDevices)
    }

    var showsInMyStuff: Bool {
        !dismissedFromMyStuff && completedCount < totalCount
    }

    var progressText: String {
        "\(completedCount) of \(totalCount) done"
    }
}

/// One live example shown under Row 1's inline search box: tonight's game,
/// an award, or an election (`364: A`).
nonisolated struct FirstRunLookupExample364A: Identifiable, Equatable, Sendable {
    enum Kind: String, Equatable, Sendable {
        case game
        case award
        case election
    }

    let id: String
    let kind: Kind
    let badgeText: String
    let title: String
    let query: String
    let percent: Int
    let imageUrl: String?
    let sfSymbol: String
}

/// Live result card shown inside Row 1's standalone `"Look anything up"` step.
nonisolated struct FirstRunLookupResult364A: Identifiable, Equatable, Sendable {
    let id: String
    let badgeText: String
    let title: String
    let subtitle: String
    let percent: Int
    let imageUrl: String?
    let sfSymbol: String
    let accentHex: String
}

/// One of the three live cards under `"Start with tonight"`:
/// biggest game on, biggest mover, and one odd one (`364: A`).
nonisolated struct FirstRunTonightCard364A: Identifiable, Equatable, Sendable {
    let id: String
    let slotLabel: String
    let title: String
    let subtitle: String
    let percent: Int
    let deltaText: String?
    let imageUrl: String?
    let sfSymbol: String
    let accentHex: String
}

/// Small live picture and real probability shown directly on each checklist row (`364: A`).
nonisolated struct FirstRunChecklistRowPreview364A: Equatable, Sendable {
    let subtitle: String
    let percentText: String?
    let imageUrl: String?
    let sfSymbol: String
    let accentHex: String
}

/// One Discover set shown inside Row 3 (`"See what the world expects"`) in its real
/// served native card form (`MachineryDiscoverEntryCardView`).
nonisolated struct FirstRunSetChoice364A: Identifiable, Sendable {
    let slug: String
    let bundleTitle: String
    let category: String
    let imageUrl: String?
    let machineryCard: MachineryCardContract
    let pairedMetricSet: PairedMetricSet?
    let leadPercent: Int

    var id: String { slug }
}

/// Complete immutable live-backed dataset powering the `364: A` checklist sheet & steps.
nonisolated struct FirstRunChecklistContent364A: Sendable {
    static let butlerQuote = "\u{201C}Probability is the very guide of life.\u{201D} Joseph Butler, 1736"

    let lookupExamples: [FirstRunLookupExample364A]
    let startWithTonight: [FirstRunTonightCard364A]
    let discoverSets: [FirstRunSetChoice364A]
    let rowPreviews: [FirstRunChecklistRowID364A: FirstRunChecklistRowPreview364A]
    let subjectArtByCategory: [String: String]

    var lookupRowPreview: FirstRunChecklistRowPreview364A? { rowPreviews[.lookUp] }
    var followRowPreview: FirstRunChecklistRowPreview364A? { rowPreviews[.follow] }
    var setsRowPreview: FirstRunChecklistRowPreview364A? { rowPreviews[.exploreSets] }
    var syncRowPreview: FirstRunChecklistRowPreview364A? { rowPreviews[.syncDevices] }
    var alertsRowPreview: FirstRunChecklistRowPreview364A? { rowPreviews[.alerts] }
}

/// Maps non-sports subject categories & labels on Row 2 (`"Follow what you care about"`)
/// to real served banner art URLs extracted from the feed so non-sports subjects carry
/// real pictures alongside team logos (`364: A`).
nonisolated enum FirstRunSubjectArt364A {
    static func extractSubjectArt(from feedItems: [FeedItem]) -> [String: String] {
        var map: [String: String] = [:]

        func assign(_ key: String, url: String?) {
            guard map[key] == nil, let clean = cleanHTTPS(url) else { return }
            map[key] = clean
        }

        for item in feedItems {
            if let ev = item.event {
                assign("team:\(ev.homeTeam.lowercased())", url: ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge)
                assign("team:\(ev.awayTeam.lowercased())", url: ev.awayTeamData?.logoSmall ?? ev.awayTeamData?.logoLarge)
            }
            if let bundle = item.bundle {
                for child in bundle.items {
                    if let ev = child.event {
                        assign("team:\(ev.homeTeam.lowercased())", url: ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge)
                        assign("team:\(ev.awayTeam.lowercased())", url: ev.awayTeamData?.logoSmall ?? ev.awayTeamData?.logoLarge)
                    }
                }
                let bLower = bundle.title.lowercased()
                let bIdLower = bundle.id.lowercased()
                let bSlug = (bundle.roundupContract?.machineryCard?.slug ?? bundle.collectionRef?.slug ?? "").lowercased()
                let bImg = bundle.roundupContract?.machineryCard?.imageUrl
                    ?? bundle.imageUrl
                    ?? bundle.items.compactMap { $0.futures?.imageUrl }.first

                if bLower.contains("oscar") || bSlug.contains("oscar") {
                    assign("awards", url: bImg)
                    assign("entertainment", url: bImg)
                }
                if bIdLower.contains("story:macro_rates") || bLower.contains("fed") || bLower.contains("inflation") || bLower.contains("rate") {
                    assign("economy", url: bImg)
                    assign("economics", url: bImg)
                }
                if bIdLower.contains("story:ai") || bLower == "ai" || bSlug == "ai" || bLower.contains("tech") {
                    assign("tech", url: bImg)
                    assign("ai", url: bImg)
                }
                if bSlug.contains("climate") || bSlug.contains("highs") || bLower.contains("wettest") {
                    assign("weather", url: bImg)
                }
                if bLower.contains("bond") || bSlug.contains("bond") || bLower.contains("engaged") {
                    assign("entertainment", url: bImg)
                }
                if bLower.contains("chess") {
                    assign("chess", url: bImg)
                }
            }
            if let fut = item.futures {
                let cls = FirstRunPair212A.classifyFuturesCategory(fut)
                if !cls.isSports, !FirstRunPair212A.isGrimOrSensitiveTopic(title: fut.name) {
                    assign(cls.categoryKey, url: fut.imageUrl)
                }
            }
        }
        return map
    }

    static func imageURL(
        for suggestion: FirstRunSuggestion212A,
        subjectArt: [String: String]
    ) -> String? {
        if let logo = cleanHTTPS(suggestion.logoUrl) {
            return logo
        }
        let nameLower = suggestion.name.lowercased()
        if let teamLogo = subjectArt["team:\(nameLower)"] {
            return teamLogo
        }
        let kindLower = suggestion.sportOrCategoryLabel.lowercased()
        if nameLower.contains("oscar") || kindLower == "awards" {
            return subjectArt["awards"] ?? subjectArt["entertainment"]
        }
        if nameLower.contains("inflation") || nameLower.contains("fed") || kindLower == "economy" {
            return subjectArt["economy"] ?? subjectArt["economics"]
        }
        if nameLower == "ai" || kindLower == "tech" {
            return subjectArt["ai"] ?? subjectArt["tech"]
        }
        if kindLower == "weather" || nameLower.contains("weather") {
            return subjectArt["weather"]
        }
        if let aff = suggestion.affinityCategory?.lowercased(), let url = subjectArt[aff] {
            return url
        }
        return nil
    }

    static func attachingPictures(
        to suggestions: [FirstRunSuggestion212A],
        subjectArt: [String: String]
    ) -> [FirstRunSuggestion212A] {
        suggestions.map { item in
            guard item.logoUrl == nil,
                  let resolved = imageURL(for: item, subjectArt: subjectArt) else {
                return item
            }
            return FirstRunSuggestion212A(
                id: item.id,
                name: item.name,
                sportOrCategoryLabel: item.sportOrCategoryLabel,
                contextLine: item.contextLine,
                logoUrl: resolved,
                primaryColorHex: item.primaryColorHex,
                teamId: item.teamId,
                sportKey: item.sportKey,
                followedSubject: item.followedSubject,
                affinityCategory: item.affinityCategory,
                marketId: item.marketId,
                matchKeywords: item.matchKeywords
            )
        }
    }

    fileprivate static func cleanHTTPS(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              let url = URL(string: trimmed),
              url.scheme?.lowercased() == "https",
              url.host?.isEmpty == false else {
            return nil
        }
        return trimmed
    }
}

/// Pure extractor turning live `/api/feed` Discover + Sports payloads into `364: A` checklist data.
nonisolated enum FirstRunChecklistExtractor364A {
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

    private static func parseDate(_ raw: String?) -> Date? {
        guard let s = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else {
            return nil
        }
        return isoWithFractional.date(from: s) ?? isoStandard.date(from: s)
    }

    private static func boundedPercent(rawProb: Double?, rendered: Int?) -> Int? {
        let pct: Int
        if let rendered {
            pct = rendered
        } else if let rawProb, rawProb.isFinite {
            let scaled = (rawProb > 1.0 && rawProb <= 100.0) ? rawProb : rawProb * 100.0
            pct = Int(scaled.rounded())
        } else {
            return nil
        }
        guard (5...95).contains(pct) else { return nil }
        return pct
    }

    private static func flattenedEvents(from feedItems: [FeedItem]) -> [FeedEventData] {
        var out: [FeedEventData] = []
        var seen: Set<Int> = []
        for item in feedItems {
            if let ev = item.event, seen.insert(ev.id).inserted {
                out.append(ev)
            } else if let bundle = item.bundle {
                for child in bundle.items {
                    if let ev = child.event, seen.insert(ev.id).inserted {
                        out.append(ev)
                    }
                }
            }
        }
        return out
    }

    private static func rankedGamesWithin24h(from feedItems: [FeedItem], now: Date) -> [(prio: Int, seq: Int, event: FeedEventData, pct: Int, shortTitle: String, deltaPoints: Int?)] {
        let earliest = now.addingTimeInterval(-4 * 3600)
        let latest = now.addingTimeInterval(24 * 3600)
        var list: [(prio: Int, seq: Int, event: FeedEventData, pct: Int, shortTitle: String, deltaPoints: Int?)] = []

        for (idx, ev) in flattenedEvents(from: feedItems).enumerated() {
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { continue }
            guard let prio = FirstRunPair212A.leaguePriority(for: ev.sport) else { continue }
            guard let start = parseDate(ev.commenceTime), start >= earliest, start <= latest else { continue }
            let curProb = ev.currentOdds?.homeProbability ?? ev.openingOdds?.homeProbability
            guard let pct = boundedPercent(rawProb: curProb, rendered: ev.currentOdds?.homeRenderedPercent) else {
                continue
            }
            let pairs = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
            let prevProb = ev.prematchOdds?.homeProbability ?? ev.openingOdds?.homeProbability
            var deltaPts: Int?
            if let curProb, let prevProb, curProb.isFinite, prevProb.isFinite {
                let p1 = curProb > 1.0 ? curProb / 100.0 : curProb
                let p0 = prevProb > 1.0 ? prevProb / 100.0 : prevProb
                let diff = Int(((p1 - p0) * 100.0).rounded())
                if diff != 0 { deltaPts = diff }
            }
            list.append((prio, idx, ev, pct, "\(pairs.away) at \(pairs.home)", deltaPts))
        }

        list.sort { lhs, rhs in
            if lhs.prio != rhs.prio { return lhs.prio < rhs.prio }
            return lhs.seq < rhs.seq
        }
        return list
    }

    static func buildContent(from feedItems: [FeedItem], now: Date = Date()) -> FirstRunChecklistContent364A {
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let rankedGames = rankedGamesWithin24h(from: feedItems, now: now)
        let lookupExamples = extractLookupExamples(from: feedItems, rankedGames: rankedGames, subjectArt: subjectArt, now: now)
        let tonight = extractStartWithTonight(from: feedItems, rankedGames: rankedGames, subjectArt: subjectArt, now: now)
        let sets = extractDiscoverSets(from: feedItems, limit: 5, now: now)

        var previews: [FirstRunChecklistRowID364A: FirstRunChecklistRowPreview364A] = [:]

        if let leadGame = lookupExamples.first(where: { $0.kind == .game }) ?? lookupExamples.first {
            previews[.lookUp] = FirstRunChecklistRowPreview364A(
                subtitle: "No account needed",
                percentText: "\(leadGame.percent)%",
                imageUrl: leadGame.imageUrl,
                sfSymbol: leadGame.sfSymbol,
                accentHex: "#005CC2"
            )
        }

        if let secondGame = (rankedGames.dropFirst().first ?? rankedGames.first) {
            let art = FirstRunSubjectArt364A.cleanHTTPS(secondGame.event.homeTeamData?.logoSmall ?? secondGame.event.homeTeamData?.logoLarge)
            previews[.follow] = FirstRunChecklistRowPreview364A(
                subtitle: "Teams, cities, schools & subjects",
                percentText: "\(secondGame.pct)%",
                imageUrl: art,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: secondGame.event.sport), isSports: true),
                accentHex: "#047857"
            )
        }

        if let leadSet = sets.first {
            previews[.exploreSets] = FirstRunChecklistRowPreview364A(
                subtitle: "Tap the ones you\u{2019}d open",
                percentText: "\(leadSet.leadPercent)%",
                imageUrl: leadSet.imageUrl,
                sfSymbol: "square.stack.3d.up.fill",
                accentHex: "#7C3AED"
            )
        }

        previews[.syncDevices] = FirstRunChecklistRowPreview364A(
            subtitle: "Follow or pick first",
            percentText: nil,
            imageUrl: nil,
            sfSymbol: "iphone.and.ipad",
            accentHex: "#005CC2"
        )

        if let mover = tonight.first(where: { $0.slotLabel == "Biggest mover" }) ?? tonight.first {
            previews[.alerts] = FirstRunChecklistRowPreview364A(
                subtitle: "Game starts & big moves",
                percentText: "\(mover.percent)%",
                imageUrl: mover.imageUrl,
                sfSymbol: "bell.badge.fill",
                accentHex: "#D97706"
            )
        }

        return FirstRunChecklistContent364A(
            lookupExamples: lookupExamples,
            startWithTonight: tonight,
            discoverSets: sets,
            rowPreviews: previews,
            subjectArtByCategory: subjectArt
        )
    }

    private static func isConflictOrGrimBundleOrMarket(_ text: String) -> Bool {
        if FirstRunPair212A.isGrimOrSensitiveTopic(title: text) {
            return true
        }
        let lower = text.lowercased()
        return lower.contains("conflict")
            || lower.contains("middle_east")
            || lower.contains("middle east")
            || lower.contains("russia_ukraine")
            || lower.contains("war")
            || lower.contains("israel")
            || lower.contains("gaza")
            || lower.contains("ukraine")
    }

    private static func conciseChipTitle(for rawTitle: String, kind: FirstRunLookupExample364A.Kind) -> String {
        switch kind {
        case .award:
            if rawTitle.lowercased().hasPrefix("oscar winner: ") {
                return "Oscars: " + rawTitle.dropFirst("Oscar Winner: ".count)
            }
            return rawTitle
        case .election:
            let lower = rawTitle.lowercased()
            if lower.contains("french presidential election") {
                return "French Election"
            }
            if lower.contains("prime minister of spain") {
                return "Spain Prime Minister"
            }
            return rawTitle
        case .game:
            return rawTitle
        }
    }

    static func extractLookupExamples(
        from feedItems: [FeedItem],
        now: Date = Date()
    ) -> [FirstRunLookupExample364A] {
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let games = rankedGamesWithin24h(from: feedItems, now: now)
        return extractLookupExamples(from: feedItems, rankedGames: games, subjectArt: subjectArt, now: now)
    }

    private static func extractLookupExamples(
        from feedItems: [FeedItem],
        rankedGames: [(prio: Int, seq: Int, event: FeedEventData, pct: Int, shortTitle: String, deltaPoints: Int?)],
        subjectArt: [String: String],
        now: Date
    ) -> [FirstRunLookupExample364A] {
        var out: [FirstRunLookupExample364A] = []

        // 1. Tonight's game
        if let g = rankedGames.first {
            let shortHome = TeamShortName.shortPair(away: g.event.awayTeam, home: g.event.homeTeam, sportKey: g.event.sport).home
            out.append(FirstRunLookupExample364A(
                id: "lookup-game-\(g.event.id)",
                kind: .game,
                badgeText: "Tonight",
                title: g.shortTitle,
                query: shortHome,
                percent: g.pct,
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(g.event.homeTeamData?.logoSmall ?? g.event.homeTeamData?.logoLarge),
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: g.event.sport), isSports: true)
            ))
        }

        // Collect all non-grim, conflict-free unsettled futures in feed order
        var futuresWithBundle: [(fut: FeedFuturesData, bundleImg: String?)] = []
        var seenFutIds: Set<Int> = []
        for item in feedItems {
            if let fut = item.futures, seenFutIds.insert(fut.id).inserted {
                guard !isConflictOrGrimBundleOrMarket(fut.name) else { continue }
                futuresWithBundle.append((fut, fut.imageUrl))
            } else if let bundle = item.bundle {
                let bundleDescriptor = "\(bundle.id) \(bundle.title) \(bundle.roundupContract?.kicker ?? "")"
                guard !isConflictOrGrimBundleOrMarket(bundleDescriptor) else { continue }
                let bImg = bundle.roundupContract?.machineryCard?.imageUrl ?? bundle.imageUrl
                for child in bundle.items {
                    if let fut = child.futures, seenFutIds.insert(fut.id).inserted {
                        guard !isConflictOrGrimBundleOrMarket(fut.name) else { continue }
                        futuresWithBundle.append((fut, fut.imageUrl ?? bImg))
                    }
                }
            }
        }

        // 2. An award (prefer non-sports award like Oscars over sports awards like Heisman)
        let awardCandidates = futuresWithBundle.compactMap { entry -> (isNonSports: Bool, fut: FeedFuturesData, img: String?, pct: Int)? in
            let fut = entry.fut
            guard !FeedLifecycle.futuresIsSettled(fut, now: now) else { return nil }
            let lower = fut.name.lowercased()
            let isNonSportsAward = fut.sport == nil && (
                lower.contains("oscar")
                || lower.contains("grammy")
                || lower.contains("emmy")
                || lower.contains("golden globe")
                || lower.contains("game of the year")
            )
            let isSportsAward = lower.contains("heisman") || lower.contains("mvp")
            guard isNonSportsAward || isSportsAward else { return nil }
            guard let resolved = FirstRunPair212A.resolvePrimaryOutcome(for: fut),
                  (5...95).contains(resolved.percent) else { return nil }
            return (isNonSportsAward, fut, entry.bundleImg, resolved.percent)
        }
        if let chosenAward = awardCandidates.first(where: \.isNonSports) ?? awardCandidates.first {
            let lower = chosenAward.fut.name.lowercased()
            out.append(FirstRunLookupExample364A(
                id: "lookup-award-\(chosenAward.fut.id)",
                kind: .award,
                badgeText: "Award",
                title: conciseChipTitle(for: chosenAward.fut.name, kind: .award),
                query: lower.contains("oscar") ? "Oscars" : chosenAward.fut.name,
                percent: chosenAward.pct,
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(chosenAward.img) ?? subjectArt["awards"] ?? subjectArt["entertainment"],
                sfSymbol: "trophy.fill"
            ))
        }

        // 3. An election (conflict-free, non-grim, 5...95%)
        for (fut, img) in futuresWithBundle {
            guard !FeedLifecycle.futuresIsSettled(fut, now: now) else { continue }
            let lower = fut.name.lowercased()
            let isElection = lower.contains("election") || lower.contains("presidential") || lower.contains("prime minister")
            guard isElection else { continue }
            guard let resolved = FirstRunPair212A.resolvePrimaryOutcome(for: fut),
                  (5...95).contains(resolved.percent) else { continue }
            let queryTerm = lower.contains("french") ? "France" : (lower.contains("spain") ? "Spain" : "elections")
            out.append(FirstRunLookupExample364A(
                id: "lookup-election-\(fut.id)",
                kind: .election,
                badgeText: "Election",
                title: conciseChipTitle(for: fut.name, kind: .election),
                query: queryTerm,
                percent: resolved.percent,
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(img),
                sfSymbol: "building.columns.fill"
            ))
            break
        }

        return out
    }

    static func extractStartWithTonight(
        from feedItems: [FeedItem],
        now: Date = Date()
    ) -> [FirstRunTonightCard364A] {
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let games = rankedGamesWithin24h(from: feedItems, now: now)
        return extractStartWithTonight(from: feedItems, rankedGames: games, subjectArt: subjectArt, now: now)
    }

    private static func extractStartWithTonight(
        from feedItems: [FeedItem],
        rankedGames: [(prio: Int, seq: Int, event: FeedEventData, pct: Int, shortTitle: String, deltaPoints: Int?)],
        subjectArt: [String: String],
        now: Date
    ) -> [FirstRunTonightCard364A] {
        var cards: [FirstRunTonightCard364A] = []
        var usedEventIds: Set<Int> = []

        // 1. Biggest game on tonight
        if let topGame = rankedGames.first {
            usedEventIds.insert(topGame.event.id)
            let pairs = TeamShortName.shortPair(away: topGame.event.awayTeam, home: topGame.event.homeTeam, sportKey: topGame.event.sport)
            let league = sportDisplayName(for: topGame.event.sport)
            cards.append(FirstRunTonightCard364A(
                id: "tonight-game-\(topGame.event.id)",
                slotLabel: "Biggest game",
                title: topGame.shortTitle,
                subtitle: league.isEmpty ? pairs.home : "\(league) \u{00B7} \(pairs.home)",
                percent: topGame.pct,
                deltaText: FirstRunCard212A.shiftText(points: topGame.deltaPoints),
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(topGame.event.homeTeamData?.logoSmall ?? topGame.event.homeTeamData?.logoLarge),
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: topGame.event.sport), isSports: true),
                accentHex: topGame.event.homeTeamData?.primaryColor ?? "#047857"
            ))
        }

        // 2. Biggest mover (largest |delta| among unsettled 5...95% games/markets)
        var moverCandidates: [(absDelta: Int, card: FirstRunTonightCard364A)] = []
        for ev in flattenedEvents(from: feedItems) where !usedEventIds.contains(ev.id) {
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { continue }
            let curProb = ev.currentOdds?.homeProbability
            let prevProb = ev.prematchOdds?.homeProbability ?? ev.openingOdds?.homeProbability
            guard let curProb, let prevProb, curProb.isFinite, prevProb.isFinite else { continue }
            guard let pct = boundedPercent(rawProb: curProb, rendered: ev.currentOdds?.homeRenderedPercent) else { continue }
            let p1 = curProb > 1.0 ? curProb / 100.0 : curProb
            let p0 = prevProb > 1.0 ? prevProb / 100.0 : prevProb
            let diff = Int(((p1 - p0) * 100.0).rounded())
            guard abs(diff) >= 2 else { continue }
            let pairs = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
            let league = sportDisplayName(for: ev.sport)
            moverCandidates.append((
                abs(diff),
                FirstRunTonightCard364A(
                    id: "tonight-mover-ev-\(ev.id)",
                    slotLabel: "Biggest mover",
                    title: "\(pairs.away) at \(pairs.home)",
                    subtitle: league.isEmpty ? pairs.home : "\(league) \u{00B7} \(pairs.home)",
                    percent: pct,
                    deltaText: FirstRunCard212A.shiftText(points: diff),
                    imageUrl: FirstRunSubjectArt364A.cleanHTTPS(ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge),
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: ev.sport), isSports: true),
                    accentHex: "#D97706"
                )
            ))
        }
        moverCandidates.sort { $0.absDelta > $1.absDelta }
        if let bestMover = moverCandidates.first {
            cards.append(bestMover.card)
        }

        // 3. One odd one (top Discover ODD / curiosity item in 5...95%, non-grim, Yes-side)
        for item in feedItems {
            guard let bundle = item.bundle else { continue }
            let tagUpper = (bundle.roundupContract?.tag ?? bundle.roundupContract?.kicker ?? "").uppercased()
            let isOdd = tagUpper.contains("ODD") || bundle.title.lowercased().contains("mars") || bundle.title.lowercased().contains("chess")
            guard isOdd else { continue }
            for child in bundle.items {
                guard let fut = child.futures else { continue }
                guard !FeedLifecycle.futuresIsSettled(fut, now: now) else { continue }
                guard !FirstRunPair212A.isGrimOrSensitiveTopic(title: fut.name) else { continue }
                guard let resolved = FirstRunPair212A.resolvePrimaryOutcome(for: fut),
                      (5...95).contains(resolved.percent) else { continue }
                let subTitle = resolved.outcomeName ?? "Yes"
                let img = FirstRunSubjectArt364A.cleanHTTPS(fut.imageUrl ?? bundle.roundupContract?.machineryCard?.imageUrl ?? bundle.imageUrl)
                    ?? subjectArt[FirstRunPair212A.classifyFuturesCategory(fut).categoryKey]
                cards.append(FirstRunTonightCard364A(
                    id: "tonight-odd-\(fut.id)",
                    slotLabel: "Odd one",
                    title: fut.name,
                    subtitle: subTitle,
                    percent: resolved.percent,
                    deltaText: FirstRunCard212A.shiftText(points: resolved.deltaPoints),
                    imageUrl: img,
                    sfSymbol: "sparkles",
                    accentHex: "#7C3AED"
                ))
                return cards
            }
        }

        return cards
    }

    static func extractDiscoverSets(
        from feedItems: [FeedItem],
        limit: Int = 5,
        now: Date = Date()
    ) -> [FirstRunSetChoice364A] {
        var candidates: [FirstRunSetChoice364A] = []
        var seenSlugs: Set<String> = []

        for item in feedItems {
            guard let bundle = item.bundle,
                  let card = bundle.roundupContract?.machineryCard,
                  !card.slug.isEmpty,
                  seenSlugs.insert(card.slug).inserted else {
                continue
            }
            guard !FirstRunPair212A.isGrimOrSensitiveTopic(title: "\(bundle.title) \(card.title) \(card.kicker)") else {
                continue
            }

            // Respect Fable's 5...95% rule across displayed rows inside the card,
            // including `paired_stage_bars` whose rows sit on `roundupContract.rows`.
            let rowPcts: [Int]
            if !card.outcomeRows.isEmpty {
                rowPcts = card.outcomeRows.map(\.renderedPercent)
            } else if !card.eventRows.isEmpty {
                rowPcts = card.eventRows.flatMap { [$0.awayPct, $0.homePct] }
            } else {
                rowPcts = (bundle.roundupContract?.rows ?? []).compactMap { row in
                    if let rendered = row.renderedPercent { return rendered }
                    let p = row.probability
                    let scaled = (p > 1.0 && p <= 100.0) ? p : p * 100.0
                    return Int(scaled.rounded())
                }
            }
            guard let leadPct = rowPcts.first, (5...95).contains(leadPct) else {
                continue
            }
            if rowPcts.contains(where: { $0 < 5 || $0 > 95 }) {
                continue
            }

            let rawImg = FirstRunSubjectArt364A.cleanHTTPS(card.imageUrl ?? bundle.imageUrl)
            let pset = bundle.roundupContract?.pairedMetricSet ?? bundle.pairedMetricSet
            candidates.append(FirstRunSetChoice364A(
                slug: card.slug,
                bundleTitle: bundle.title,
                category: card.kicker,
                imageUrl: rawImg,
                machineryCard: card,
                pairedMetricSet: pset,
                leadPercent: leadPct
            ))
        }

        // Prefer sets with public HTTPS photos (deprioritizing api.bainluck.com), pick distinct native forms
        // first (`paired_stage_bars`, `sibling_fields_grid`, `benchmark_strip`), then diversify domains/categories.
        let nonAppHost = candidates.filter { !($0.imageUrl?.lowercased().contains("api.bainluck.com") ?? false) }
        let appHost = candidates.filter { $0.imageUrl?.lowercased().contains("api.bainluck.com") ?? false }
        let ordered = nonAppHost + appHost

        func primaryDomain(for category: String) -> String {
            let first = category.split(separator: "\u{00B7}").first?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() ?? ""
            if first.contains("OSCAR") || first.contains("ENTERTAINMENT") {
                return "CULTURE"
            }
            return first
        }

        var selected: [FirstRunSetChoice364A] = []
        var usedForms: Set<MachineryFormId> = []
        var usedDomains: Set<String> = []
        var usedKickers: Set<String> = []

        func appendChoice(_ choice: FirstRunSetChoice364A) {
            selected.append(choice)
            usedForms.insert(choice.machineryCard.formId)
            usedDomains.insert(primaryDomain(for: choice.category))
            usedKickers.insert(choice.category.uppercased())
        }

        let formPreferredOrder = ordered.sorted { lhs, rhs in
            func rank(_ f: MachineryFormId) -> Int {
                switch f {
                case .pairedStageBars: return 0
                case .siblingFieldsGrid: return 1
                default: return 2
                }
            }
            return rank(lhs.machineryCard.formId) < rank(rhs.machineryCard.formId)
        }

        for choice in formPreferredOrder where !usedForms.contains(choice.machineryCard.formId) {
            appendChoice(choice)
            if selected.count >= limit { return selected }
        }
        for choice in ordered where !selected.contains(where: { $0.slug == choice.slug }) {
            let domain = primaryDomain(for: choice.category)
            if !domain.isEmpty, !usedDomains.contains(domain) {
                appendChoice(choice)
                if selected.count >= limit { return selected }
            }
        }
        for choice in ordered where !selected.contains(where: { $0.slug == choice.slug }) {
            let key = choice.category.uppercased()
            if !key.isEmpty, !usedKickers.contains(key) {
                appendChoice(choice)
                if selected.count >= limit { return selected }
            }
        }
        for choice in ordered where !selected.contains(where: { $0.slug == choice.slug }) {
            appendChoice(choice)
            if selected.count >= limit { break }
        }
        return selected
    }
}
