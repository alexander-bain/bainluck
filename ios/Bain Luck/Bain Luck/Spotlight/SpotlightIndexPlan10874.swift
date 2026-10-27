import Foundation

/// #10874 — what this device may put in Spotlight: the reader's own saved and
/// recently viewed games and markets, described by facts that do not go stale.
///
/// Identity is `StoryContinuationDestination`, the canonical event/market
/// identity Handoff already uses; the Spotlight identifier is its canonical
/// `https://bainluck.com/{events|futures}/{id}` URL, so activation goes through
/// the same strict round trip and the same `handleURL` as a Universal Link.
/// Nothing here merges providers or invents an identity: one canonical id, one
/// entry.
///
/// Never in the index: a probability, a price, a score or a live/settled state.
/// Spotlight can show an entry long after it was written, so it carries only
/// the subject, its competition or category and its date; opening it loads the
/// detail page's own current, dated, settled or unavailable state.

/// The stable description of one game or market, as the detail page (or My
/// Stuff's hydration from the same detail payload) last saw it.
nonisolated struct SpotlightSubject10874: Codable, Equatable, Sendable {
    nonisolated enum Kind: String, Codable, Sendable { case game, market }

    let kind: Kind
    let id: Int
    /// What the reader would type: "Away at Home", or the market's own name.
    let title: String
    /// "NFL", "Politics" — never a raw key; empty when unknown.
    let competition: String
    /// A game's scheduled day. Markets carry none: their dates are not stable.
    let date: Date?
    /// Words a reader may search by: each team's name, the competition.
    let aliases: [String]

    var destination: StoryContinuationDestination {
        switch kind {
        case .game: return .event(id)
        case .market: return .futures(id)
        }
    }

    /// The Spotlight identifier, or `nil` for an id the identity contract refuses.
    var identifier: String? { StoryContinuation.url(for: destination)?.absoluteString }

    /// A game, from the fields every event payload carries. `nil` without both
    /// team names or a valid id, so a half-loaded page indexes nothing.
    /// Main-actor because the app's display-name helpers are.
    /// The detail page and My Stuff build it from the same fields, so the two
    /// never disagree about one game and rewrite each other.
    @MainActor static func game(id: Int, away: String, home: String, sportKey: String?,
                                commenceTime: String?) -> Self? {
        let away = away.trimmingCharacters(in: .whitespacesAndNewlines)
        let home = home.trimmingCharacters(in: .whitespacesAndNewlines)
        guard id > 0, !away.isEmpty, !home.isEmpty else { return nil }
        let competition = sportDisplayName(for: sportKey)
        return Self(kind: .game, id: id, title: "\(away) at \(home)", competition: competition,
                    date: commenceTime?.asDate,
                    aliases: SpotlightIndexPlan10874.aliases([away, home, competition]))
    }

    /// A market, by the name its own page shows and its category.
    @MainActor static func market(id: Int, name: String, category: String?) -> Self? {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard id > 0, !name.isEmpty else { return nil }
        let competition = category.map { sportCategoryDisplayName($0) } ?? ""
        return Self(kind: .market, id: id, title: name, competition: competition, date: nil,
                    aliases: SpotlightIndexPlan10874.aliases([competition]))
    }
}

/// One subject the reader has met on this device: when they last actually
/// viewed its detail page (`nil` when it is only known because it is saved).
nonisolated struct SpotlightEntry10874: Codable, Equatable, Sendable {
    var subject: SpotlightSubject10874
    var viewedAt: Date?
}

/// What My Stuff learned about one saved pin from its detail payload.
nonisolated enum SpotlightSavedAnswer10874: Equatable, Sendable {
    case described(SpotlightSubject10874)
    /// The server answered 404/410: the item is gone.
    case gone
}

/// What is handed to Spotlight for one entry. Plain data, so every rule about
/// content is a unit test; only the production client turns it into a
/// `CSSearchableItem`.
///
/// No start date: Spotlight prints an item's `startDate` as a clock under the
/// title ("Sun 10:00 AM", seen on the simulator), and a placeholder start has
/// an unreal clock. A game's day reaches the reader only through `detail`.
nonisolated struct SpotlightIndexItem10874: Equatable, Sendable {
    let identifier: String
    let domain: String
    let title: String
    let detail: String
    let keywords: [String]
    let expiration: Date
}

nonisolated enum SpotlightIndexPlan10874 {
    /// Every domain this feature writes sits under this root, so one delete of
    /// the root clears every account's entries at once.
    static let rootDomain = "com.bainluck.spotlight10874"

    /// Retention for recently viewed, unsaved subjects: the newest
    /// `recentLimit` actually viewed within `recentWindow`. Saved subjects are
    /// kept while saved; their number is already capped by
    /// `PinManager.maxPinsPerType` per type, which this never changes.
    static let recentLimit = 25
    static let recentWindow: TimeInterval = 14 * 86_400
    /// Spotlight drops a saved entry on its own if the app is not opened for
    /// this long; any later sync writes it again.
    static let savedExpiry: TimeInterval = 30 * 86_400
    /// A detail page must stay on screen this long, in the foreground and
    /// loaded, to count as viewed — a page swiped straight past is not a visit.
    static let viewDwell: TimeInterval = 2

    /// The account's index domain. Only one account's entries exist at a
    /// time (`SpotlightIndex10874.bind` purges the root first); the account
    /// segment keeps a straggler attributable rather than anonymous.
    static func domain(scope: String) -> String { "\(rootDomain).\(scope)" }

    /// The per-account scope, mirroring `PinManager`'s storage namespace.
    static func scope(userID: String?) -> String {
        guard let userID, !userID.isEmpty else { return "guest" }
        let safe = userID.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) ? String($0) : "-" }.joined()
        return "user-\(safe)"
    }

    static func isRecent(_ entry: SpotlightEntry10874, now: Date) -> Bool {
        guard let viewedAt = entry.viewedAt else { return false }
        return viewedAt <= now.addingTimeInterval(60) && now.timeIntervalSince(viewedAt) < recentWindow
    }

    /// The entries worth keeping: every saved one this account still has a
    /// description for, plus the newest `recentLimit` recent ones. Everything
    /// else — expired, beyond the limit, or no longer saved and never viewed —
    /// is forgotten, on disk and (through `items`) in Spotlight.
    static func prune(_ entries: [SpotlightEntry10874], saved: Set<StoryContinuationDestination>,
                      now: Date) -> [SpotlightEntry10874] {
        var seen = Set<StoryContinuationDestination>()
        let unique = entries.filter { seen.insert($0.subject.destination).inserted }
        let recent = unique
            .filter { !saved.contains($0.subject.destination) && isRecent($0, now: now) }
            .sorted { ($0.viewedAt ?? .distantPast) > ($1.viewedAt ?? .distantPast) }
            .prefix(recentLimit)
        let keep = Set(recent.map(\.subject.destination))
            .union(saved.intersection(unique.map(\.subject.destination)))
        return unique.filter { keep.contains($0.subject.destination) }
    }

    /// What Spotlight should hold for these entries, now.
    static func items(_ entries: [SpotlightEntry10874], saved: Set<StoryContinuationDestination>,
                      scope: String, now: Date) -> [SpotlightIndexItem10874] {
        prune(entries, saved: saved, now: now).compactMap { entry in
            guard let identifier = entry.subject.identifier else { return nil }
            let isSaved = saved.contains(entry.subject.destination)
            // Day-granular, so a saved entry is not rewritten on every sync.
            let savedUntil = Calendar(identifier: .gregorian).startOfDay(for: now).addingTimeInterval(savedExpiry)
            let recentUntil = (entry.viewedAt ?? now).addingTimeInterval(recentWindow)
            return SpotlightIndexItem10874(
                identifier: identifier, domain: domain(scope: scope),
                title: entry.subject.title, detail: detail(entry.subject),
                keywords: entry.subject.aliases,
                expiration: isSaved ? max(savedUntil, recentUntil) : recentUntil)
        }
    }

    /// "NFL · Sun, Oct 18, 2026" for a game; "Politics" for a market. The date
    /// tells two meetings of the same teams apart; no time of day, because a
    /// placeholder start (`startIsTbd`) has a real day and an unreal clock.
    static func detail(_ subject: SpotlightSubject10874, locale: Locale = .current,
                       timeZone: TimeZone = .current) -> String {
        var parts: [String] = []
        if !subject.competition.isEmpty { parts.append(subject.competition) }
        if let date = subject.date {
            let style = Date.FormatStyle(locale: locale, calendar: Calendar(identifier: .gregorian), timeZone: timeZone)
                .weekday(.abbreviated).month(.abbreviated).day().year()
            parts.append(date.formatted(style))
        }
        return parts.joined(separator: " · ")
    }

    /// The writes that turn `applied` into `desired`: changed or new items,
    /// then identifiers no longer wanted.
    static func diff(applied: [String: SpotlightIndexItem10874], desired: [SpotlightIndexItem10874])
        -> (upserts: [SpotlightIndexItem10874], deletes: [String]) {
        let wanted = Set(desired.map(\.identifier))
        let upserts = desired.filter { applied[$0.identifier] != $0 }
        let deletes = applied.keys.filter { !wanted.contains($0) }.sorted()
        return (upserts, deletes)
    }

    static func aliases(_ names: [String?]) -> [String] {
        var seen = Set<String>()
        return names.compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
    }
}

/// #10874 — a Spotlight result the reader tapped, back to its exact page.
nonisolated enum SpotlightActivation10874 {
    /// The canonical URL for a tapped result, or `nil` for anything that is
    /// not exactly one of ours. `actionType` is `CSSearchableItemActionType`;
    /// `identifier` is the activity's `CSSearchableItemActivityIdentifier`.
    /// No fallback: an identifier that does not round-trip opens nothing,
    /// rather than the first event that looks similar.
    static func url(activityType: String, actionType: String, identifier: Any?) -> URL? {
        guard activityType == actionType, let raw = identifier as? String,
              let destination = StoryContinuation.destination(from: URL(string: raw)) else { return nil }
        return StoryContinuation.url(for: destination)
    }
}
