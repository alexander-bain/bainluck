import Combine
import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Ruling 295: A — Follow & My Stuff First (#11934)

nonisolated enum FollowedSubjectKind295A: String, Codable, Hashable, Sendable {
    case team
    case league
    case set
    case subject
}

nonisolated enum FollowedSetKind295A: String, Codable, Hashable, Sendable {
    case container
    case tournament
    case golfTournament
    case concept
}

nonisolated struct FollowedSubject295A: Codable, Identifiable, Hashable, Sendable {
    let kind: FollowedSubjectKind295A
    let slug: String
    var teamId: Int? = nil
    var sportKey: String? = nil
    var setKind: FollowedSetKind295A? = nil
    var marketId: Int? = nil
    var affinityCategory: String? = nil
    var searchQuery: String? = nil
    let name: String
    var logoUrl: String? = nil
    var primaryColor: String? = nil
    var followedAt: Date = Date()

    var id: String {
        switch kind {
        case .team:
            return "team:\(Self.normalizeSlug(slug))"
        case .league:
            return "league:\(Self.normalizeSlug(slug))"
        case .set:
            let subtype = setKind?.rawValue ?? "container"
            return "set:\(subtype):\(slug.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())"
        case .subject:
            return "subject:\(Self.normalizeSlug(slug))"
        }
    }

    var route: Route {
        switch kind {
        case .team:
            if let teamId, slug.isEmpty {
                return .teamDetail(slug: "\(teamId)")
            }
            return .teamDetail(slug: slug)
        case .league:
            if slug == "golf" || sportKey == "golf" {
                return .golfCategory
            }
            if slug.hasPrefix("tennis_") || (sportKey?.hasPrefix("tennis_") == true) {
                let key = sportKey ?? slug
                return .sportCategory(key: key, name: name)
            }
            return .leagueGrid(slug: slug)
        case .set:
            switch setKind ?? .container {
            case .container:
                return .containerHub(slug: slug, name: name)
            case .tournament:
                return .tournamentHub(slug: slug, name: name)
            case .golfTournament:
                return .golfTournament(slug: slug, name: name)
            case .concept:
                return .conceptCard(key: slug, name: name)
            }
        case .subject:
            if let marketId, marketId > 0 {
                return .futuresDetail(id: marketId)
            }
            let key = "\(affinityCategory ?? "") \(slug) \(name)".lowercased()
            if key.contains("entertainment") || key.contains("award") || key.contains("oscar")
                || key.contains("culture") || key.contains("movie") || key.contains("music") {
                return .entertainment
            }
            if key.contains("econ") || key.contains("macro") || key.contains("inflation")
                || key.contains("fed") || key.contains("rate") || key.contains("finance") {
                return .economics
            }
            if key.contains("politic") || key.contains("geopolitic") || key.contains("election") {
                return .politics
            }
            if key.contains("weather") || key.contains("climate") {
                return .weather
            }
            return .futuresList
        }
    }

    static func normalizeSlug(_ raw: String) -> String {
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let parts = lower.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
        return parts.joined(separator: "-")
    }

    static func isIndividualSport(_ sportKey: String?) -> Bool {
        guard let key = sportKey?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !key.isEmpty else {
            return false
        }
        return key.hasPrefix("tennis")
            || key.hasPrefix("golf")
            || key.hasPrefix("mma")
            || key.hasPrefix("boxing")
            || key.hasPrefix("motorsports")
    }

    static func team(
        slug: String,
        teamId: Int? = nil,
        name: String,
        sportKey: String? = nil,
        logoUrl: String? = nil,
        primaryColor: String? = nil
    ) -> FollowedSubject295A {
        let cleanSlug = slug.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? normalizeSlug(name)
            : slug.trimmingCharacters(in: .whitespacesAndNewlines)
        return FollowedSubject295A(
            kind: .team,
            slug: cleanSlug,
            teamId: teamId,
            sportKey: sportKey,
            setKind: nil,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            logoUrl: logoUrl,
            primaryColor: primaryColor
        )
    }

    static func teamFromEventSide(event: FeedEventData, isHome: Bool) -> FollowedSubject295A? {
        guard !isIndividualSport(event.sport) else { return nil }
        let rawName = (isHome ? event.homeTeam : event.awayTeam).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawName.isEmpty, rawName.uppercased() != "TBD" else { return nil }
        let data = isHome ? event.homeTeamData : event.awayTeamData
        let servedSlug = data?.slug?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedSlug: String
        if let servedSlug, !servedSlug.isEmpty {
            resolvedSlug = servedSlug
        } else if let tid = data?.teamId, tid > 0 {
            resolvedSlug = "\(tid)"
        } else {
            resolvedSlug = normalizeSlug(rawName)
        }
        guard !resolvedSlug.isEmpty else { return nil }
        return FollowedSubject295A(
            kind: .team,
            slug: resolvedSlug,
            teamId: data?.teamId,
            sportKey: event.sport,
            setKind: nil,
            name: rawName,
            logoUrl: data?.logoSmall ?? data?.logoLarge,
            primaryColor: data?.primaryColor
        )
    }

    nonisolated struct EventCardTeamEntry295A: Sendable {
        let subject: FollowedSubject295A
        let shortName: String
        let opponentName: String
    }

    static func eventCardTeams(for event: FeedEventData) -> (away: EventCardTeamEntry295A?, home: EventCardTeamEntry295A?) {
        let shorts = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let away = teamFromEventSide(event: event, isHome: false).map {
            EventCardTeamEntry295A(subject: $0, shortName: shorts.away, opponentName: event.homeTeam)
        }
        let home = teamFromEventSide(event: event, isHome: true).map {
            EventCardTeamEntry295A(subject: $0, shortName: shorts.home, opponentName: event.awayTeam)
        }
        return (away, home)
    }

    static func league(slug: String, sportKey: String, name: String) -> FollowedSubject295A {
        FollowedSubject295A(
            kind: .league,
            slug: slug.trimmingCharacters(in: .whitespacesAndNewlines),
            teamId: nil,
            sportKey: sportKey.trimmingCharacters(in: .whitespacesAndNewlines),
            setKind: nil,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }

    static func set(slug: String, setKind: FollowedSetKind295A, name: String) -> FollowedSubject295A {
        FollowedSubject295A(
            kind: .set,
            slug: slug.trimmingCharacters(in: .whitespacesAndNewlines),
            teamId: nil,
            sportKey: nil,
            setKind: setKind,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }

    static func subject(
        slug: String,
        name: String,
        affinityCategory: String? = nil,
        marketId: Int? = nil,
        logoUrl: String? = nil,
        primaryColor: String? = nil,
        searchQuery: String? = nil
    ) -> FollowedSubject295A {
        FollowedSubject295A(
            kind: .subject,
            slug: slug.trimmingCharacters(in: .whitespacesAndNewlines),
            teamId: nil,
            sportKey: nil,
            setKind: nil,
            marketId: marketId,
            affinityCategory: affinityCategory?.trimmingCharacters(in: .whitespacesAndNewlines),
            searchQuery: searchQuery?.trimmingCharacters(in: .whitespacesAndNewlines),
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            logoUrl: logoUrl,
            primaryColor: primaryColor
        )
    }

    func matches(_ other: FollowedSubject295A) -> Bool {
        if id == other.id { return true }
        if kind == .subject && other.kind == .subject {
            if let lhsId = marketId, lhsId > 0, let rhsId = other.marketId, rhsId > 0 {
                return lhsId == rhsId
            }
            let lhsSlug = Self.normalizeSlug(slug)
            let rhsSlug = Self.normalizeSlug(other.slug)
            return !lhsSlug.isEmpty && lhsSlug == rhsSlug
        }
        guard kind == .team && other.kind == .team else { return false }

        let lhsValidId = (teamId ?? 0) > 0 ? teamId : nil
        let rhsValidId = (other.teamId ?? 0) > 0 ? other.teamId : nil

        // Explicit team IDs always win when both sides carry one.
        if let lhsId = lhsValidId, let rhsId = rhsValidId {
            return lhsId == rhsId
        }

        let lhsSlug = Self.normalizeSlug(slug)
        let rhsSlug = Self.normalizeSlug(other.slug)
        let lhsIsNumericSlug = !lhsSlug.isEmpty && lhsSlug.allSatisfy(\.isNumber)
        let rhsIsNumericSlug = !rhsSlug.isEmpty && rhsSlug.allSatisfy(\.isNumber)

        // Non-numeric canonical slug equality (respecting sportKey when both have one).
        if !lhsSlug.isEmpty, !lhsIsNumericSlug, !rhsIsNumericSlug, lhsSlug == rhsSlug {
            if let s1 = sportKey?.lowercased(), let s2 = other.sportKey?.lowercased(), !s1.isEmpty, !s2.isEmpty {
                return s1 == s2 || s1.split(separator: "_").first == s2.split(separator: "_").first
            }
            return true
        }

        // Name fallback is restricted strictly to subjects where NEITHER side has a teamId
        // and BOTH sides carry matching non-empty sport keys.
        guard lhsValidId == nil && rhsValidId == nil else { return false }
        guard let s1 = sportKey?.lowercased(), let s2 = other.sportKey?.lowercased(), !s1.isEmpty, !s2.isEmpty else {
            return false
        }
        let sameSportFamily = s1 == s2 || s1.split(separator: "_").first == s2.split(separator: "_").first
        guard sameSportFamily else { return false }

        let lhsNameSlug = Self.normalizeSlug(name)
        let rhsNameSlug = Self.normalizeSlug(other.name)
        return !lhsNameSlug.isEmpty && lhsNameSlug == rhsNameSlug
    }
}

/// Pure rules for Ruling 295: A — My Stuff-first landing & tab bar order.
enum MyStuffLandingRule295A {
    /// My Stuff moves to the left of the tab bar for everyone.
    static let orderedTabs: [AppTab] = [.myStuff, .discover, .feed, .leagues, .search]

    /// A reader who follows or pins at least one thing opens on My Stuff;
    /// a reader with nothing followed or pinned still opens on Discover.
    static func initialTab(
        followedCount: Int,
        pinnedCount: Int,
        hasPersistedServerFollows: Bool = false
    ) -> AppTab {
        if followedCount > 0 || pinnedCount > 0 || hasPersistedServerFollows {
            return .myStuff
        }
        return .discover
    }
}

final class FollowManager295A: ObservableObject {
    static let shared = FollowManager295A()

    static let subjectsPrefName = "bainluck_followed_subjects"
    static let serverFavoritesFlagName = "bainluck_server_favorites_nonempty"
    static let locallyUnfollowedIdsPrefName = "bainluck_locally_unfollowed_team_ids"

    typealias TeamFavoriteSync = @Sendable (_ teamId: Int, _ following: Bool) async -> Void

    @Published private(set) var subjects: [FollowedSubject295A] = []

    private let defaults: UserDefaults
    private let teamSync: TeamFavoriteSync?
    private var isAuthenticated: Bool = false

    init(
        defaults: UserDefaults = .standard,
        initialSubjects: [FollowedSubject295A]? = nil,
        teamSync: TeamFavoriteSync? = nil
    ) {
        self.defaults = defaults
        self.teamSync = teamSync
        if let initialSubjects {
            self.subjects = initialSubjects
            save()
        } else {
            load()
        }
    }

    var hasFollows: Bool { !subjects.isEmpty }

    var hasPersistedServerFollows: Bool {
        defaults.bool(forKey: Self.serverFavoritesFlagName)
    }

    func setAuthenticated(_ authenticated: Bool) {
        isAuthenticated = authenticated
    }

    @MainActor
    func recordServerFavoritesCount(_ count: Int) {
        defaults.set(count > 0, forKey: Self.serverFavoritesFlagName)
    }

    @MainActor
    func mergeServerFavorites(_ favorites: [FavoriteItem]) {
        let suppressedIds = loadLocallyUnfollowedTeamIds()
        let activeFavorites = favorites.filter { $0.relationType != "rival" && !suppressedIds.contains($0.teamId) }
        defaults.set(!activeFavorites.isEmpty, forKey: Self.serverFavoritesFlagName)
        var changed = false
        for fav in activeFavorites {
            let candidate = FollowedSubject295A.team(
                slug: "\(fav.teamId)",
                teamId: fav.teamId,
                name: fav.teamName,
                sportKey: fav.sportKey,
                logoUrl: fav.logoUrl
            )
            if !isFollowing(candidate) {
                subjects.append(candidate)
                changed = true
            }
        }
        if changed { save() }
    }

    func isFollowing(_ subject: FollowedSubject295A) -> Bool {
        subjects.contains { $0.matches(subject) }
    }

    /// Toggles follow state in one tap with no account required.
    /// Returns `true` when the subject is now followed, `false` when unfollowed.
    @MainActor
    @discardableResult
    func toggle(_ subject: FollowedSubject295A) -> Bool {
        if let idx = subjects.firstIndex(where: { $0.matches(subject) }) {
            let removed = subjects.remove(at: idx)
            if let tid = removed.teamId, tid > 0 {
                markLocallyUnfollowed(teamId: tid, unfollowed: true)
            }
            if subjects.isEmpty {
                defaults.set(false, forKey: Self.serverFavoritesFlagName)
            }
            save()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            #endif
            syncServerTeamIfNeeded(removed, following: false)
            return false
        } else {
            var added = subject
            added.followedAt = Date()
            if let tid = added.teamId, tid > 0 {
                markLocallyUnfollowed(teamId: tid, unfollowed: false)
            }
            subjects.insert(added, at: 0)
            save()
            #if os(iOS)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            #endif
            syncServerTeamIfNeeded(added, following: true)
            return true
        }
    }

    private func loadLocallyUnfollowedTeamIds() -> Set<Int> {
        let arr = defaults.array(forKey: Self.locallyUnfollowedIdsPrefName) as? [Int] ?? []
        return Set(arr)
    }

    private func markLocallyUnfollowed(teamId: Int, unfollowed: Bool) {
        var current = loadLocallyUnfollowedTeamIds()
        if unfollowed {
            current.insert(teamId)
        } else {
            current.remove(teamId)
        }
        defaults.set(Array(current).sorted(), forKey: Self.locallyUnfollowedIdsPrefName)
    }

    private func syncServerTeamIfNeeded(_ subject: FollowedSubject295A, following: Bool) {
        guard subject.kind == .team, let teamId = subject.teamId, teamId > 0 else { return }
        if let teamSync {
            Task { await teamSync(teamId, following) }
            return
        }
        guard isAuthenticated else { return }
        let defaultsRef = defaults
        Task {
            if following {
                _ = try? await APIClient.shared.addFavorite(teamId: teamId, relationType: "follow")
            } else if (try? await APIClient.shared.removeFavorite(teamId: teamId, relationType: "follow")) != nil {
                var set = Set((defaultsRef.array(forKey: Self.locallyUnfollowedIdsPrefName) as? [Int]) ?? [])
                set.remove(teamId)
                defaultsRef.set(Array(set).sorted(), forKey: Self.locallyUnfollowedIdsPrefName)
            }
        }
    }

    private func load() {
        guard let data = defaults.data(forKey: Self.subjectsPrefName),
              let decoded = try? JSONDecoder().decode([FollowedSubject295A].self, from: data) else {
            subjects = []
            return
        }
        subjects = decoded
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(subjects) else { return }
        defaults.set(data, forKey: Self.subjectsPrefName)
    }
}

private struct FollowManagerEnvironmentKey295A: EnvironmentKey {
    static let defaultValue: FollowManager295A = .shared
}

extension EnvironmentValues {
    var followManager295A: FollowManager295A {
        get { self[FollowManagerEnvironmentKey295A.self] }
        set { self[FollowManagerEnvironmentKey295A.self] = newValue }
    }
}
