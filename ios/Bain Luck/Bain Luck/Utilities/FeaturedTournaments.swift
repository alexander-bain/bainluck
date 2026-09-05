import Foundation

/// A tournament that has its own hub screen, promoted so a person can reach it
/// without knowing it exists.
///
/// This used to be a `private` list inside `LeaguesView`, which meant Browse was
/// the only surface that could offer one. Search — where a person who wants the
/// US Open actually goes first — could not see the list at all.
nonisolated struct FeaturedTournament: Identifiable, Equatable, Sendable {
    /// The API slug, e.g. `us-open` for `/api/tournaments/us-open`.
    let slug: String
    let title: String
    let subtitle: String
    let icon: String
    /// Other names for the same tournament. Matched exactly like the title is:
    /// every token of an alias must be present in the query.
    let aliases: [String]

    init(slug: String, title: String, subtitle: String, icon: String, aliases: [String] = []) {
        self.slug = slug
        self.title = title
        self.subtitle = subtitle
        self.icon = icon
        self.aliases = aliases
    }

    var id: String { slug }
}

/// Tournament hubs promoted to Browse, and offered by Search when a query names one.
///
/// HAND-MAINTAINED, and that is the known limitation rather than the design:
/// `REGISTERED_TOURNAMENTS` lives on the server and is not exposed as a list, so
/// the phone cannot ask which hubs exist or which one is being played this week.
/// A slug listed here stays listed after its final — the hub itself degrades
/// honestly (it keeps serving results and the finished board), but Browse will
/// keep offering the US Open in March until either this list is edited or the
/// API grows an index. Tracked as a follow-up; not worth blocking the hub on.
let featuredTournaments: [FeaturedTournament] = [
    FeaturedTournament(
        slug: "us-open",
        title: "US Open",
        subtitle: "Live matches, results, title odds",
        icon: "tennis.racket",
        aliases: ["flushing meadows"]
    ),
]

// MARK: - Naming a hub from its slug

/// The title to show for a hub slug that arrived from a link.
///
/// `Route.tournamentHub` carries a display name because the hub screen shows it
/// as the navigation title while the payload loads and in the error state — so
/// a link has to supply one. The catalog above is the authority when it knows
/// the slug (`us-open` → `US Open`); anything else falls back to the shared
/// acronym-safe title caser, which is what keeps a slug the catalog has not
/// heard of from rendering as "Us Open" (#1938's class of defect). The loaded
/// hub renders the server's own name regardless — this only owns the title bar.
nonisolated func tournamentDisplayName(
    forSlug slug: String,
    in catalog: [FeaturedTournament] = featuredTournaments
) -> String {
    if let known = catalog.first(where: { $0.slug == slug }) { return known.title }
    return toTitleCaseAcronymSafe(slug.replacingOccurrences(of: "-", with: " "))
}

// MARK: - Matching a search query to a hub

/// The tokens of `text`, lowercased, split on everything that is not a letter or digit.
///
/// `"U.S. Open"` → `["u", "s", "open"]`, `"US  Open!"` → `["us", "open"]`.
private func searchTokens(_ text: String) -> [String] {
    text.lowercased()
        .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
        .map(String.init)
}

/// `text` with every non-alphanumeric character removed: `"U.S. Open"` → `"usopen"`.
private func collapsed(_ text: String) -> String {
    text.lowercased().filter { $0.isLetter || $0.isNumber }
}

/// The token spellings of a name that a query may reasonably use.
///
/// A leading article is optional in the way people actually type: nobody searching
/// for The Open Championship types "the", and nobody searching for The Masters
/// types it either. Dropping it is safe because the REST of the name is still
/// required in full — `"open"` alone matches neither form.
private func nameForms(_ name: String) -> [[String]] {
    let tokens = searchTokens(name)
    guard let first = tokens.first else { return [] }
    let articles: Set<String> = ["the", "a", "an"]
    if tokens.count > 1, articles.contains(first) {
        return [tokens, Array(tokens.dropFirst())]
    }
    return [tokens]
}

/// Whether `query` names `name`.
///
/// Two ways to match, and deliberately no third:
///
/// 1. **Every token of the name is a token of the query.** `"us open"` and
///    `"us open tennis"` and `"the us open"` all name the US Open; `"open"` alone
///    does not, and neither does `"us"`. Requiring ALL tokens is what keeps the
///    generic half of a two-word name from matching on its own — otherwise every
///    query containing "open" would offer a tennis hub.
/// 2. **The query, stripped to letters and digits, equals the stripped name.**
///    This is only for punctuation and spacing: `"U.S. Open"`, `"usopen"`,
///    `"us-open"`. It is an equality and not a `contains` on purpose — a substring
///    test matches `"housopener"`, which names nothing.
private func query(_ query: String, names name: String) -> Bool {
    let queryTokens = Set(searchTokens(query))
    guard !queryTokens.isEmpty else { return false }
    let collapsedQuery = collapsed(query)

    for form in nameForms(name) {
        if form.allSatisfy({ queryTokens.contains($0) }) { return true }

        let collapsedName = form.joined()
        if collapsedQuery == collapsedName { return true }
        // "usopen" typed as one word, alongside other terms.
        if queryTokens.contains(collapsedName) { return true }
    }
    return false
}

/// The featured hubs a search query names, in catalog order.
///
/// Returns empty for a query that names no tournament, which is the common case —
/// the caller draws nothing rather than a "no tournaments" row.
func featuredTournaments(
    matching searchQuery: String,
    in catalog: [FeaturedTournament] = featuredTournaments
) -> [FeaturedTournament] {
    catalog.filter { tournament in
        query(searchQuery, names: tournament.title)
            || tournament.aliases.contains { query(searchQuery, names: $0) }
    }
}
