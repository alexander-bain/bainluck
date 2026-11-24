import Combine
import Foundation
import SwiftUI

// MARK: - Decision 364: A — Single-Screen Five-Row First-Run Checklist (#11934)

nonisolated enum FirstRunStorageKeys364A {
    static let checklistStateKey = "bainluck_first_run_checklist_state_364a"
}

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

/// Persistent store backing the `364: A` checklist across the launch sheet and My Stuff banner.
@MainActor
final class FirstRunChecklistStore364A: ObservableObject {
    static let shared = FirstRunChecklistStore364A()

    @Published var state: FirstRunChecklistState364A {
        didSet {
            guard state != oldValue else { return }
            save()
        }
    }

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: FirstRunStorageKeys364A.checklistStateKey),
           let decoded = try? JSONDecoder().decode(FirstRunChecklistState364A.self, from: data) {
            self.state = decoded
        } else {
            self.state = .untouched
        }
    }

    func markCompleted(_ row: FirstRunChecklistRowID364A) {
        var next = state
        next.completedRows.insert(row)
        state = next
    }

    func syncFollowCount(_ count: Int, markFollowCompleted: Bool = false) {
        var next = state
        next.followedCount = max(0, count)
        if markFollowCompleted && count > 0 {
            next.completedRows.insert(.follow)
        }
        state = next
    }

    func syncAuthState(isAuthenticated: Bool) {
        guard isAuthenticated else { return }
        markCompleted(.syncDevices)
    }

    func syncAlertsState(isEnabled: Bool) {
        guard isEnabled else { return }
        markCompleted(.alerts)
    }

    func setSelectedSetSlugs(_ slugs: Set<String>, from sets: [FirstRunSetChoice364A]) {
        var next = state
        next.selectedSetSlugs = slugs
        if !slugs.isEmpty {
            next.completedRows.insert(.exploreSets)
        }
        state = next
        persistPickedSetsToDiscoverPreferences(slugs: slugs, sets: sets)
    }

    func dismissFromMyStuff() {
        var next = state
        next.dismissedFromMyStuff = true
        state = next
    }

    func resetForRedoOnboarding() {
        state = .untouched
    }

    private func persistPickedSetsToDiscoverPreferences(slugs: Set<String>, sets: [FirstRunSetChoice364A]) {
        guard !slugs.isEmpty else { return }
        var prefs = FirstRunPreferences212A.load(defaults: defaults)
        var categories = Set(prefs.boostedCategories)
        var terms = Set(prefs.boostedTerms)

        for choice in sets where slugs.contains(choice.slug) {
            let cat = FirstRunSetCategoryMapper364A.discoverCategory(for: choice.category, title: choice.bundleTitle)
            if !cat.isEmpty {
                categories.insert(cat)
            }
            if !choice.bundleTitle.isEmpty {
                terms.insert(choice.bundleTitle)
            }
        }

        prefs.boostedCategories = Array(categories).sorted()
        prefs.boostedTerms = Array(terms).sorted()
        prefs.save(defaults: defaults)
    }

    private func save() {
        if let data = try? JSONEncoder().encode(state) {
            defaults.set(data, forKey: FirstRunStorageKeys364A.checklistStateKey)
        }
    }
}

private struct FirstRunChecklistStoreEnvironmentKey364A: EnvironmentKey {
    @MainActor static var defaultValue: FirstRunChecklistStore364A { .shared }
}

extension EnvironmentValues {
    var firstRunChecklistStore364A: FirstRunChecklistStore364A {
        get { self[FirstRunChecklistStoreEnvironmentKey364A.self] }
        set { self[FirstRunChecklistStoreEnvironmentKey364A.self] = newValue }
    }
}

private nonisolated enum FirstRunSetCategoryMapper364A {
    static func discoverCategory(for kicker: String, title: String) -> String {
        let lower = "\(kicker) \(title)".lowercased()
        if lower.contains("oscar") || lower.contains("grammy") || lower.contains("emmy")
            || lower.contains("entertainment") || lower.contains("bond") || lower.contains("culture") {
            return "entertainment"
        }
        if lower.contains("econ") || lower.contains("fed") || lower.contains("inflation") || lower.contains("rate") {
            return "economics"
        }
        if lower.contains("weather") || lower.contains("climate") {
            return "weather"
        }
        if lower.contains("tech") || lower.contains("ai") {
            return "tech"
        }
        if lower.contains("politic") || lower.contains("election") || lower.contains("france") || lower.contains("spain") {
            return "politics"
        }
        return ""
    }
}

/// One live example shown under Row 1's inline search box: tonight's game,
/// an award, or an election (`364: A`). Every percent sits with its subject.
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
    let percent: Int?
    let imageUrl: String?
    let sfSymbol: String
    var route: Route? = nil
}

/// Live result card shown inside Row 1's standalone `"Look anything up"` step.
nonisolated struct FirstRunLookupResult364A: Identifiable, Equatable, Sendable {
    let id: String
    let badgeText: String
    let title: String
    let subtitle: String
    let subjectLabel: String
    let percent: Int
    let imageUrl: String?
    let sfSymbol: String
    let accentHex: String
    var route: Route? = nil
}

/// One of the three live cards under `"Start with tonight"`:
/// biggest game on, biggest mover, and one odd one (`364: A`).
nonisolated struct FirstRunTonightCard364A: Identifiable, Equatable, Sendable {
    let id: String
    let slotLabel: String
    let title: String
    let subtitle: String
    var subjectLabel: String = ""
    let percent: Int
    let deltaText: String?
    var deltaPoints: Int? = nil
    var startTimeText: String? = nil
    let imageUrl: String?
    let sfSymbol: String
    let accentHex: String
    var route: Route? = nil
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

    private static func favoredArt(
        homeTeamData: TeamData?,
        awayTeamData: TeamData?,
        homeImageUrl: String?,
        awayImageUrl: String?,
        homeFavored: Bool
    ) -> (logoUrl: String?, accentHex: String?) {
        let teamData = homeFavored ? homeTeamData : awayTeamData
        let fallbackImage = homeFavored ? homeImageUrl : awayImageUrl
        let logo = FirstRunSubjectArt364A.cleanHTTPS(teamData?.logoSmall ?? teamData?.logoLarge ?? fallbackImage)
        return (logo, teamData?.primaryColor)
    }

    private static func favoredArt(for event: FeedEventData, homeFavored: Bool) -> (logoUrl: String?, accentHex: String?) {
        favoredArt(
            homeTeamData: event.homeTeamData,
            awayTeamData: event.awayTeamData,
            homeImageUrl: event.homeImageUrl,
            awayImageUrl: event.awayImageUrl,
            homeFavored: homeFavored
        )
    }

    private static func favoredArt(for event: SearchEvent, homeFavored: Bool) -> (logoUrl: String?, accentHex: String?) {
        favoredArt(
            homeTeamData: event.homeTeamData,
            awayTeamData: event.awayTeamData,
            homeImageUrl: event.homeImageUrl,
            awayImageUrl: event.awayImageUrl,
            homeFavored: homeFavored
        )
    }

    private typealias RankedGameEntry = (
        isMajorLeague: Bool,
        isWithin24h: Bool,
        prio: Int,
        seq: Int,
        event: FeedEventData,
        favoredTeam: String,
        pct: Int,
        shortTitle: String,
        favoredLogoUrl: String?,
        favoredAccentHex: String?,
        deltaPoints: Int?,
        deltaWindow: String?,
        startTimeText: String?
    )

    private static let startTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "h:mm a"
        return f
    }()

    private static func rankedGamesWithin24h(
        from feedItems: [FeedItem],
        previousSnapshot: [String: Double],
        now: Date
    ) -> [RankedGameEntry] {
        let earliest = now.addingTimeInterval(-4 * 3600)
        let cutoff24h = now.addingTimeInterval(24 * 3600)
        let latest = now.addingTimeInterval(36 * 3600)
        var list: [RankedGameEntry] = []

        for (idx, ev) in flattenedEvents(from: feedItems).enumerated() {
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { continue }
            guard let prio = FirstRunPair212A.leaguePriority(for: ev.sport) else { continue }
            guard let start = parseDate(ev.commenceTime), start >= earliest, start <= latest else { continue }
            let curHomeProb = ev.currentOdds?.homeProbability ?? ev.prematchOdds?.homeProbability
            let curAwayProb = ev.currentOdds?.awayProbability ?? ev.prematchOdds?.awayProbability
            let duel = duelPercents(
                away: curAwayProb,
                home: curHomeProb,
                servedAway: ev.currentOdds != nil ? ev.currentOdds?.awayRenderedPercent : nil,
                servedHome: ev.currentOdds != nil ? ev.currentOdds?.homeRenderedPercent : nil
            )
            guard let homePct = duel[1], (5...95).contains(homePct) else {
                continue
            }
            let awayPct = duel[0] ?? (100 - homePct)
            let pairs = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
            let homeFavored = homePct >= awayPct
            let favoredTeam: String
            let favoredPct: Int
            if homeFavored {
                favoredTeam = pairs.home
                favoredPct = homePct
            } else {
                favoredTeam = pairs.away
                favoredPct = awayPct
            }
            guard (5...95).contains(favoredPct) else { continue }

            let art = favoredArt(for: ev, homeFavored: homeFavored)

            let baseline = resolvedEventBaseline(event: ev, previousSnapshot: previousSnapshot)
            var deltaPts: Int?
            var deltaWindow: String?
            if let curHomeProb, let baseline, curHomeProb.isFinite, baseline.prob.isFinite {
                let p1 = curHomeProb > 1.0 ? curHomeProb / 100.0 : curHomeProb
                let p0 = baseline.prob > 1.0 ? baseline.prob / 100.0 : baseline.prob
                let diff = Int(((p1 - p0) * 100.0).rounded())
                if diff != 0 {
                    deltaPts = diff
                    deltaWindow = baseline.window
                }
            }
            let startLabel: String? = (statusLower == "live" || statusLower == "in_progress")
                ? nil
                : startTimeFormatter.string(from: start)
            list.append((
                isMajorLeague: prio <= 3,
                isWithin24h: start <= cutoff24h,
                prio: prio,
                seq: idx,
                event: ev,
                favoredTeam: favoredTeam,
                pct: favoredPct,
                shortTitle: "\(pairs.away) at \(pairs.home)",
                favoredLogoUrl: art.logoUrl,
                favoredAccentHex: art.accentHex,
                deltaPoints: deltaPts,
                deltaWindow: deltaWindow,
                startTimeText: startLabel
            ))
        }

        list.sort { lhs, rhs in
            if lhs.isMajorLeague != rhs.isMajorLeague { return lhs.isMajorLeague && !rhs.isMajorLeague }
            if lhs.isWithin24h != rhs.isWithin24h { return lhs.isWithin24h && !rhs.isWithin24h }
            if lhs.prio != rhs.prio { return lhs.prio < rhs.prio }
            return lhs.seq < rhs.seq
        }
        return list
    }

    /// Only a recorded last-visit reading or the pinned pregame mark may serve as baseline (Fable fix b).
    private static func resolvedEventBaseline(
        event: FeedEventData,
        previousSnapshot: [String: Double]
    ) -> (prob: Double, window: String)? {
        if let prev = previousSnapshot["event:\(event.id)"], prev.isFinite {
            return (prev, "since your last visit")
        }
        if let prematch = event.prematchOdds?.homeProbability, prematch.isFinite {
            return (prematch, "since pregame")
        }
        return nil
    }

    static func buildContent(
        from feedItems: [FeedItem],
        defaults: UserDefaults = .standard,
        now: Date = Date()
    ) -> FirstRunChecklistContent364A {
        let previousSnapshot = MyStuffVisitLedger295A.loadPreviousSnapshot(defaults: defaults)
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let sets = extractDiscoverSets(from: feedItems, limit: 5, now: now)
        let rankedGames = rankedGamesWithin24h(from: feedItems, previousSnapshot: previousSnapshot, now: now)
        let lookupExamples = extractLookupExamples(
            from: feedItems,
            rankedGames: rankedGames,
            discoverSets: sets,
            subjectArt: subjectArt,
            now: now
        )
        let tonight = extractStartWithTonight(from: feedItems, rankedGames: rankedGames, previousSnapshot: previousSnapshot, subjectArt: subjectArt, now: now)

        var previews: [FirstRunChecklistRowID364A: FirstRunChecklistRowPreview364A] = [:]

        var usedGameEventIds: Set<Int> = []
        if let biggest = rankedGames.first {
            usedGameEventIds.insert(biggest.event.id)
        }
        if let chipGame = rankedGames.dropFirst().first ?? rankedGames.first {
            usedGameEventIds.insert(chipGame.event.id)
        }

        let secondGame = rankedGames.dropFirst(2).first ?? rankedGames.dropFirst().first ?? rankedGames.first
        if let secondGame {
            usedGameEventIds.insert(secondGame.event.id)
            previews[.follow] = FirstRunChecklistRowPreview364A(
                subtitle: "\(secondGame.favoredTeam) tonight \(secondGame.pct)% \u{00B7} teams & topics",
                percentText: nil,
                imageUrl: secondGame.favoredLogoUrl,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: secondGame.event.sport), isSports: true),
                accentHex: "#047857"
            )
        }

        if let leadSet = sets.first {
            let leadSubj = leadSetSubjectName(for: leadSet)
            let contest = conciseSetContestPhrase(for: leadSet)
            let setSubtitle: String
            if let leadSubj, let contest, !contest.isEmpty {
                setSubtitle = "\(leadSubj) \(leadSet.leadPercent)% \(contest)"
            } else if let leadSubj {
                setSubtitle = "\(leadSubj) \(leadSet.leadPercent)% to win"
            } else {
                setSubtitle = "Pick topics to browse"
            }
            previews[.exploreSets] = FirstRunChecklistRowPreview364A(
                subtitle: setSubtitle,
                percentText: nil,
                imageUrl: leadSet.imageUrl,
                sfSymbol: "square.stack.3d.up.fill",
                accentHex: "#7C3AED"
            )
        }

        previews[.syncDevices] = FirstRunChecklistRowPreview364A(
            subtitle: "Follow something first",
            percentText: nil,
            imageUrl: nil,
            sfSymbol: "laptopcomputer.and.iphone",
            accentHex: "#005CC2"
        )

        if let mover = tonight.first(where: { $0.slotLabel == "Biggest mover" }) {
            let subj = mover.subjectLabel.isEmpty ? "" : "\(mover.subjectLabel) "
            previews[.alerts] = FirstRunChecklistRowPreview364A(
                subtitle: "\(subj)\(mover.percent)% now \u{00B7} game alerts",
                percentText: nil,
                imageUrl: mover.imageUrl,
                sfSymbol: "bell.badge.fill",
                accentHex: "#D97706"
            )
        } else if let fourthGame = rankedGames.dropFirst(3).first ?? rankedGames.dropFirst().last ?? rankedGames.first {
            usedGameEventIds.insert(fourthGame.event.id)
            previews[.alerts] = FirstRunChecklistRowPreview364A(
                subtitle: "\(fourthGame.favoredTeam) tonight \(fourthGame.pct)% \u{00B7} alerts",
                percentText: nil,
                imageUrl: fourthGame.favoredLogoUrl,
                sfSymbol: "bell.badge.fill",
                accentHex: "#D97706"
            )
        }

        // Row 1 subtitle must not repeat Row 1's own first chip (`lookupExamples` game) or any other row's game.
        if let distinctGame = rankedGames.first(where: { !usedGameEventIds.contains($0.event.id) }) {
            previews[.lookUp] = FirstRunChecklistRowPreview364A(
                subtitle: "No account \u{00B7} \(distinctGame.favoredTeam) tonight \(distinctGame.pct)%",
                percentText: nil,
                imageUrl: distinctGame.favoredLogoUrl,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: distinctGame.event.sport), isSports: true),
                accentHex: "#005CC2"
            )
        } else {
            let leadChip = lookupExamples.first
            previews[.lookUp] = FirstRunChecklistRowPreview364A(
                subtitle: "No account \u{00B7} games, awards & elections",
                percentText: nil,
                imageUrl: nil,
                sfSymbol: leadChip?.sfSymbol ?? "magnifyingglass",
                accentHex: "#005CC2"
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

    private static func leadSetSubjectName(for set: FirstRunSetChoice364A) -> String? {
        if let first = set.machineryCard.outcomeRows.first?.name, !first.isEmpty {
            return first
        }
        if let first = set.pairedMetricSet?.entries.first?.subject, !first.isEmpty {
            return first
        }
        if let first = set.machineryCard.eventRows.first?.homeTeam, !first.isEmpty {
            return first
        }
        return nil
    }

    private static func conciseSetContestPhrase(for set: FirstRunSetChoice364A) -> String? {
        let parts = set.category
            .split(separator: "\u{00B7}")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if parts.count >= 2, let rawContest = parts.last {
            let formatted = rawContest == rawContest.uppercased() ? rawContest.capitalized : rawContest
            if formatted.count <= 24 {
                return "for \(formatted)"
            }
        }
        let lower = set.bundleTitle.lowercased()
        if lower.contains("best picture") { return "for Best Picture" }
        if lower.contains("james bond") { return "for Bond theme" }
        if lower.contains("president") { return "for President" }
        return nil
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

    private static func extractOscarAwardLabel(from rawTitle: String) -> String {
        var category = rawTitle
        if let colon = rawTitle.firstIndex(of: ":") {
            category = String(rawTitle[rawTitle.index(after: colon)...])
        }
        category = category.trimmingCharacters(in: .whitespacesAndNewlines)
        for suffix in [" Winner", " winner"] {
            if category.hasSuffix(suffix) {
                category = String(category.dropLast(suffix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        let lower = category.lowercased()
        if lower.contains("best picture") { return "Best Picture" }
        if lower.contains("best director") { return "Best Director" }
        if lower.contains("best actor") { return "Best Actor" }
        if lower.contains("best actress") { return "Best Actress" }
        if lower.contains("supporting actor") { return "Best Supporting Actor" }
        if lower.contains("supporting actress") { return "Best Supporting Actress" }
        if lower.contains("documentary") { return "Best Documentary" }
        return category.isEmpty ? "Oscars" : category
    }

    private static func conciseChipTitle(
        for rawTitle: String,
        outcomeName: String?,
        kind: FirstRunLookupExample364A.Kind
    ) -> String {
        let trimmedOutcome = outcomeName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let subject = (trimmedOutcome?.isEmpty == false) ? trimmedOutcome : nil
        switch kind {
        case .award:
            let lower = rawTitle.lowercased()
            if lower.contains("mvp") {
                return subject.map { "\($0) for MVP" } ?? "\(rawTitle) \u{00B7} Yes"
            }
            if lower.hasPrefix("oscar winner: ") || lower.contains("oscar") {
                let award = extractOscarAwardLabel(from: rawTitle)
                return subject.map { "\($0) \u{00B7} \(award)" } ?? "\(award) \u{00B7} Yes"
            }
            return subject.map { "\($0) \u{00B7} \(rawTitle)" } ?? "\(rawTitle) \u{00B7} Yes"
        case .election:
            let lower = rawTitle.lowercased()
            let race: String
            if lower.contains("french presidential election") {
                race = "French Election"
            } else if lower.contains("prime minister of spain") {
                race = "Spain PM"
            } else {
                race = rawTitle
            }
            return subject.map { "\($0) \u{00B7} \(race)" } ?? "\(race) \u{00B7} Yes"
        case .game:
            return rawTitle
        }
    }

    static func extractLookupExamples(
        from feedItems: [FeedItem],
        now: Date = Date()
    ) -> [FirstRunLookupExample364A] {
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let sets = extractDiscoverSets(from: feedItems, limit: 5, now: now)
        let games = rankedGamesWithin24h(from: feedItems, previousSnapshot: [:], now: now)
        return extractLookupExamples(
            from: feedItems,
            rankedGames: games,
            discoverSets: sets,
            subjectArt: subjectArt,
            now: now
        )
    }

    private static func extractLookupExamples(
        from feedItems: [FeedItem],
        rankedGames: [RankedGameEntry],
        discoverSets: [FirstRunSetChoice364A],
        subjectArt: [String: String],
        now: Date
    ) -> [FirstRunLookupExample364A] {
        var out: [FirstRunLookupExample364A] = []

        // 1. Tonight's game — prefer index 1 so rankedGames[0] stays unique to "Start with tonight"
        if let g = rankedGames.dropFirst().first ?? rankedGames.first {
            out.append(FirstRunLookupExample364A(
                id: "lookup-game-\(g.event.id)",
                kind: .game,
                badgeText: "Tonight",
                title: "\(g.favoredTeam) tonight",
                query: g.favoredTeam,
                percent: g.pct,
                imageUrl: g.favoredLogoUrl,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: g.event.sport), isSports: true),
                route: .eventDetail(id: g.event.id)
            ))
        }

        // Collect all non-grim, conflict-free unsettled futures in feed order, preferring roundup bundles
        // so that an award chip matches Row 3's set market & percent whenever both show the same contest.
        var futuresWithBundle: [(isFromRoundup: Bool, bundleSlug: String?, fut: FeedFuturesData, bundleImg: String?)] = []
        var seenFutIds: Set<Int> = []
        for item in feedItems {
            if let fut = item.futures, seenFutIds.insert(fut.id).inserted {
                guard !isConflictOrGrimBundleOrMarket(fut.name) else { continue }
                futuresWithBundle.append((false, nil, fut, fut.imageUrl))
            } else if let bundle = item.bundle {
                let bundleDescriptor = "\(bundle.id) \(bundle.title) \(bundle.roundupContract?.kicker ?? "")"
                guard !isConflictOrGrimBundleOrMarket(bundleDescriptor) else { continue }
                let bSlug = bundle.roundupContract?.machineryCard?.slug ?? bundle.collectionRef?.slug
                let fromRoundup = bundle.kind == "roundup" || bundle.roundupContract != nil
                let bImg = bundle.roundupContract?.machineryCard?.imageUrl ?? bundle.imageUrl
                for child in bundle.items {
                    if let fut = child.futures, seenFutIds.insert(fut.id).inserted {
                        guard !isConflictOrGrimBundleOrMarket(fut.name) else { continue }
                        futuresWithBundle.append((fromRoundup, bSlug, fut, fut.imageUrl ?? bImg))
                    }
                }
            }
        }

        let selectedSetSlugs = Set(discoverSets.map(\.slug))
        let setPercentByMarketId: [Int: Int] = {
            var map: [Int: Int] = [:]
            for set in discoverSets {
                for row in set.machineryCard.outcomeRows {
                    if let mid = row.marketId {
                        map[mid] = row.renderedPercent
                    }
                }
            }
            for item in feedItems {
                guard let bundle = item.bundle,
                      let slug = bundle.roundupContract?.machineryCard?.slug,
                      selectedSetSlugs.contains(slug) else { continue }
                for row in bundle.roundupContract?.rows ?? [] {
                    let pct = row.renderedPercent ?? Int(((row.probability > 1.0 && row.probability <= 100.0) ? row.probability : row.probability * 100.0).rounded())
                    if let mid = row.marketId {
                        map[mid] = map[mid] ?? pct
                    }
                }
            }
            return map
        }()

        // 2. An award (prefer non-sports award like Oscars, aligning with Row 3's exact market & percent when shared)
        let awardCandidates = futuresWithBundle.compactMap { entry -> (matchesSet: Bool, isNonSports: Bool, fut: FeedFuturesData, img: String?, outcomeName: String?, pct: Int)? in
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
            let exactMarketMatch = setPercentByMarketId[fut.id] != nil
            let sameBestPictureMarket = lower.contains("best picture") && discoverSets.contains { set in
                let titleMatch = set.bundleTitle.lowercased().contains("best picture")
                    || set.category.lowercased().contains("best picture")
                let subjMatch = leadSetSubjectName(for: set)?.caseInsensitiveCompare(resolved.outcomeName ?? "") == .orderedSame
                return titleMatch && subjMatch
            }
            let finalPct: Int = {
                if let exactPct = setPercentByMarketId[fut.id] {
                    return exactPct
                }
                if sameBestPictureMarket,
                   let matchingSet = discoverSets.first(where: {
                       ($0.bundleTitle.lowercased().contains("best picture") || $0.category.lowercased().contains("best picture"))
                           && leadSetSubjectName(for: $0)?.caseInsensitiveCompare(resolved.outcomeName ?? "") == .orderedSame
                   }) {
                    return matchingSet.leadPercent
                }
                return resolved.percent
            }()
            guard (5...95).contains(finalPct) else { return nil }
            return (exactMarketMatch || sameBestPictureMarket, isNonSportsAward, fut, entry.bundleImg, resolved.outcomeName, finalPct)
        }
        if let chosenAward = awardCandidates.first(where: { $0.isNonSports && $0.matchesSet })
            ?? awardCandidates.first(where: \.isNonSports)
            ?? awardCandidates.first {
            let lower = chosenAward.fut.name.lowercased()
            out.append(FirstRunLookupExample364A(
                id: "lookup-award-\(chosenAward.fut.id)",
                kind: .award,
                badgeText: "Award",
                title: conciseChipTitle(for: chosenAward.fut.name, outcomeName: chosenAward.outcomeName, kind: .award),
                query: lower.contains("oscar") ? "Oscars" : (chosenAward.outcomeName ?? chosenAward.fut.name),
                percent: chosenAward.pct,
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(chosenAward.img) ?? subjectArt["awards"] ?? subjectArt["entertainment"],
                sfSymbol: "trophy.fill",
                route: .futuresDetail(id: chosenAward.fut.id)
            ))
        }

        // 3. An election (conflict-free, non-grim, 5...95%, subject named on chip)
        for (_, _, fut, img) in futuresWithBundle {
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
                title: conciseChipTitle(for: fut.name, outcomeName: resolved.outcomeName, kind: .election),
                query: queryTerm,
                percent: resolved.percent,
                imageUrl: FirstRunSubjectArt364A.cleanHTTPS(img),
                sfSymbol: "building.columns.fill",
                route: .futuresDetail(id: fut.id)
            ))
            break
        }

        return out
    }

    static func extractStartWithTonight(
        from feedItems: [FeedItem],
        defaults: UserDefaults = .standard,
        now: Date = Date()
    ) -> [FirstRunTonightCard364A] {
        let previousSnapshot = MyStuffVisitLedger295A.loadPreviousSnapshot(defaults: defaults)
        let subjectArt = FirstRunSubjectArt364A.extractSubjectArt(from: feedItems)
        let games = rankedGamesWithin24h(from: feedItems, previousSnapshot: previousSnapshot, now: now)
        return extractStartWithTonight(from: feedItems, rankedGames: games, previousSnapshot: previousSnapshot, subjectArt: subjectArt, now: now)
    }

    private static func extractStartWithTonight(
        from feedItems: [FeedItem],
        rankedGames: [RankedGameEntry],
        previousSnapshot: [String: Double],
        subjectArt: [String: String],
        now: Date
    ) -> [FirstRunTonightCard364A] {
        var cards: [FirstRunTonightCard364A] = []
        var usedEventIds: Set<Int> = []

        // 1. Biggest game on tonight
        if let topGame = rankedGames.first {
            usedEventIds.insert(topGame.event.id)
            let league = sportDisplayName(for: topGame.event.sport)
            let deltaCopy = topGame.deltaWindow.flatMap { window in
                FirstRunCard212A.shiftText(points: topGame.deltaPoints, window: window)
            }
            cards.append(FirstRunTonightCard364A(
                id: "tonight-game-\(topGame.event.id)",
                slotLabel: "Biggest game",
                title: topGame.shortTitle,
                subtitle: league,
                subjectLabel: topGame.favoredTeam,
                percent: topGame.pct,
                deltaText: deltaCopy,
                deltaPoints: topGame.deltaPoints,
                startTimeText: topGame.startTimeText,
                imageUrl: topGame.favoredLogoUrl,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: topGame.event.sport), isSports: true),
                accentHex: topGame.favoredAccentHex ?? "#047857",
                route: .eventDetail(id: topGame.event.id)
            ))
        }

        // 2. Biggest mover (largest |delta| against recorded last-visit reading or pregame mark ONLY)
        var moverCandidates: [(absDelta: Int, card: FirstRunTonightCard364A)] = []
        for ev in flattenedEvents(from: feedItems) where !usedEventIds.contains(ev.id) {
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !FeedLifecycle.terminalScheduleStatuses.contains(statusLower) else { continue }
            guard let curProb = ev.currentOdds?.homeProbability,
                  let baseline = resolvedEventBaseline(event: ev, previousSnapshot: previousSnapshot),
                  curProb.isFinite, baseline.prob.isFinite else { continue }
            guard let pct = boundedPercent(rawProb: curProb, rendered: ev.currentOdds?.homeRenderedPercent) else { continue }
            let p1 = curProb > 1.0 ? curProb / 100.0 : curProb
            let p0 = baseline.prob > 1.0 ? baseline.prob / 100.0 : baseline.prob
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
                    subtitle: league,
                    subjectLabel: pairs.home,
                    percent: pct,
                    deltaText: FirstRunCard212A.shiftText(points: diff, window: baseline.window),
                    deltaPoints: diff,
                    startTimeText: parseDate(ev.commenceTime).map { startTimeFormatter.string(from: $0) },
                    imageUrl: FirstRunSubjectArt364A.cleanHTTPS(ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge ?? ev.homeImageUrl),
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: ev.sport), isSports: true),
                    accentHex: "#D97706",
                    route: .eventDetail(id: ev.id)
                )
            ))
        }
        moverCandidates.sort { $0.absDelta > $1.absDelta }
        if let bestMover = moverCandidates.first {
            cards.append(bestMover.card)
        }

        // 3. One odd one (top Discover ODD / curiosity item in 5...95%, non-grim, Yes-side, no unwindowed delta)
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
                let outcomeRaw = (resolved.outcomeName ?? "Yes").trimmingCharacters(in: .whitespacesAndNewlines)
                let outcomeLower = outcomeRaw.lowercased()
                let isYesNoBinary = (outcomeLower == "yes" || outcomeLower == "no")
                let statement = Self.declarativeOddStatement(from: fut.name)
                let img = FirstRunSubjectArt364A.cleanHTTPS(fut.imageUrl ?? bundle.roundupContract?.machineryCard?.imageUrl ?? bundle.imageUrl)
                    ?? subjectArt[FirstRunPair212A.classifyFuturesCategory(fut).categoryKey]
                cards.append(FirstRunTonightCard364A(
                    id: "tonight-odd-\(fut.id)",
                    slotLabel: "Odd one",
                    title: statement,
                    subtitle: "",
                    subjectLabel: isYesNoBinary ? "" : outcomeRaw,
                    percent: resolved.percent,
                    deltaText: nil,
                    imageUrl: img,
                    sfSymbol: "sparkles",
                    accentHex: "#7C3AED",
                    route: .futuresDetail(id: fut.id)
                ))
                return cards
            }
        }

        return cards
    }

    /// Converts an interrogative Yes/No market headline (`"Will Elon Musk visit Mars in his lifetime?"`)
    /// into a plain declarative statement (`"Elon Musk visits Mars in his lifetime"`) per Point 5.
    static func declarativeOddStatement(from raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while text.hasSuffix("?") || text.hasSuffix(".") {
            text.removeLast()
            text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let words = text.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        guard words.count >= 4, words[0].lowercased() == "will" else {
            return text
        }
        let body = Array(words.dropFirst())
        // Locate the first lowercase main verb after the subject phrase (e.g. "Elon Musk" + "visit").
        if let verbIndex = body.firstIndex(where: { word in
            guard let first = word.first else { return false }
            return first.isLowercase
        }), verbIndex > 0 {
            var rewritten = body
            rewritten[verbIndex] = thirdPersonSingularVerb(body[verbIndex])
            return rewritten.joined(separator: " ")
        }
        return body.joined(separator: " ")
    }

    private static func thirdPersonSingularVerb(_ verb: String) -> String {
        let lower = verb.lowercased()
        switch lower {
        case "be": return "is"
        case "have": return "has"
        case "do": return "does"
        case "go": return "goes"
        default:
            if lower.hasSuffix("s") || lower.hasSuffix("sh") || lower.hasSuffix("ch")
                || lower.hasSuffix("x") || lower.hasSuffix("z") || lower.hasSuffix("o") {
                return verb + "es"
            }
            if lower.hasSuffix("y"), lower.count >= 2 {
                let prev = lower[lower.index(lower.endIndex, offsetBy: -2)]
                if !"aeiou".contains(prev) {
                    return String(verb.dropLast()) + "ies"
                }
            }
            return verb + "s"
        }
    }

    /// Maps `/api/events/search` responses into real live Row 1 lookup cards (Fable fix c & d).
    static func extractLookupResults(
        from response: SearchResponse,
        subjectArt: [String: String] = [:],
        now: Date = Date()
    ) -> [FirstRunLookupResult364A] {
        var out: [FirstRunLookupResult364A] = []
        var seenIds: Set<String> = []

        for ev in response.results.prefix(6) {
            let statusLower = (ev.status ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let isSettled = FeedLifecycle.terminalScheduleStatuses.contains(statusLower)
            let rawHome = ev.currentOdds?.homeProbability ?? ev.heroProbability ?? ev.prematchOdds?.homeProbability
            let rawAway = ev.currentOdds?.awayProbability ?? ev.heroProbabilityAway ?? ev.prematchOdds?.awayProbability
            let duel = duelPercents(
                away: rawAway,
                home: rawHome,
                servedAway: ev.currentOdds != nil ? ev.currentOdds?.awayRenderedPercent : nil,
                servedHome: ev.currentOdds != nil ? ev.currentOdds?.homeRenderedPercent : nil
            )
            guard let homePct = duel[1], (1...99).contains(homePct) else { continue }
            let awayPct = duel[0] ?? (100 - homePct)
            let sportSlug = ev.sportKey ?? ev.sport
            let pairs = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: sportSlug)
            let (subjectName, displayPct) = (homePct >= awayPct) ? (pairs.home, homePct) : (pairs.away, awayPct)
            let league = sportDisplayName(for: sportSlug)
            let badge = league.isEmpty ? "Match" : league
            let sub: String = isSettled ? "Final" : (statusLower == "live" || statusLower == "in_progress" ? "Live now" : "Upcoming game")
            let art = favoredArt(for: ev, homeFavored: homePct >= awayPct)
            let rowId = "search-event-\(ev.id)"
            guard seenIds.insert(rowId).inserted else { continue }
            out.append(FirstRunLookupResult364A(
                id: rowId,
                badgeText: badge,
                title: "\(pairs.away) at \(pairs.home)",
                subtitle: sub,
                subjectLabel: subjectName,
                percent: displayPct,
                imageUrl: art.logoUrl,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: DiscoverCategory.token(forSport: sportSlug), isSports: true),
                accentHex: art.accentHex ?? "#005CC2",
                route: .eventDetail(id: ev.id)
            ))
        }

        let familyFutures = (response.futuresFamilies ?? []).map(\.headline)
        for fut in (familyFutures + response.futures).prefix(10) {
            guard fut.status != "resolved",
                  !FirstRunPair212A.isGrimOrSensitiveTopic(title: fut.name) else { continue }
            let outcomes = fut.topOutcomes ?? []
            guard let lead = outcomes.first,
                  let pct = boundedSearchPercent(lead.probability, rendered: lead.renderedPercent) else { continue }
            let rawCat = (fut.llmSportCategory ?? fut.category ?? fut.sportName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let catLower = rawCat.lowercased()
            let badge: String
            if let sport = fut.sportName, !sport.isEmpty {
                badge = sport
            } else if !rawCat.isEmpty {
                badge = rawCat.capitalized
            } else {
                badge = "Forecast"
            }
            let leadSubject = lead.name.trimmingCharacters(in: .whitespacesAndNewlines)
            let cleanTitle = MyStuffLandingViewModel295A.cleanMarketTitle(fut.name)
            let titleToShow = cleanTitle.isEmpty ? fut.name : cleanTitle
            let img = subjectArt[catLower] ?? (fut.name.lowercased().contains("oscar") ? subjectArt["awards"] ?? subjectArt["entertainment"] : nil)
            let rowId = "search-futures-\(fut.id)"
            guard seenIds.insert(rowId).inserted else { continue }
            out.append(FirstRunLookupResult364A(
                id: rowId,
                badgeText: badge,
                title: titleToShow,
                subtitle: "",
                subjectLabel: leadSubject.isEmpty ? "Yes" : leadSubject,
                percent: pct,
                imageUrl: img,
                sfSymbol: FirstRunCard212A.sfSymbol(forCategory: catLower, isSports: fut.sport != nil),
                accentHex: "#7C3AED",
                route: .futuresDetail(id: fut.id)
            ))
        }

        return Array(out.prefix(12))
    }

    private static func boundedSearchPercent(_ rawProb: Double?, rendered: Int?) -> Int? {
        let pct: Int
        if let rendered {
            pct = rendered
        } else if let rawProb, rawProb.isFinite {
            let scaled = (rawProb > 1.0 && rawProb <= 100.0) ? rawProb : rawProb * 100.0
            pct = Int(scaled.rounded())
        } else {
            return nil
        }
        guard (1...99).contains(pct) else { return nil }
        return pct
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
