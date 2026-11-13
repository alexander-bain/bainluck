import AppIntents
import Foundation

/// #10873 / #12315 — Siri and Spotlight in-app search (`ShowInAppSearchResultsIntent`).
///
/// On build 5704, Siri heard `"Open My Stuff in Bain Luck"` as a system in-app
/// search (`"can't search for 'My Stuff' inside Bain Luck because the app doesn't
/// support in-app search"`), and Spotlight's `"kc"` / `"kansas city football"`
/// lacked `"Search in Bain Luck"`.
///
/// `SearchInBainLuckTerm10873` keeps the routing rule pure and unit-tested:
/// 1. Trim leading/trailing whitespace; empty terms open nothing (`nil`).
/// 2. Whole-phrase My Stuff terms (`"my stuff"`, `"my saved games"`, `"saved"`,
///    `"my pins"`, case-insensitive) route to `IntentLinks10873.myStuff` so Siri
///    hearing `"Open My Stuff in Bain Luck"` as a search still lands on My Stuff.
/// 3. Everything else routes to `bainluck://search?q=<trimmed>` via
///    `IntentRouteHandoff10873.shared`, which closes any presented sheet or
///    full-screen chart first (#12478) and hands the query to `SearchView`.
nonisolated enum SearchInBainLuckTerm10873 {
    static let myStuffPhrases: Set<String> = [
        "my stuff",
        "my saved games",
        "saved",
        "my pins",
    ]

    static func destination(for rawTerm: String) -> URL? {
        let trimmed = rawTerm.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let collapsed = trimmed
            .lowercased()
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
        if myStuffPhrases.contains(collapsed) {
            return IntentLinks10873.myStuff
        }
        return IntentLinks10873.search(query: trimmed)
    }
}

@available(iOS 18.0, macOS 15.0, visionOS 2.0, *)
@AppIntent(schema: .system.search)
struct SearchInBainLuckIntent10873: ShowInAppSearchResultsIntent {
    static let title: LocalizedStringResource = "Search Bain Luck"
    static let searchScopes: [StringSearchScope] = [.general]
    static let openAppWhenRun: Bool = true

    @Parameter(title: "Search Term", requestValueDialog: "What would you like to search for?")
    var criteria: StringSearchCriteria

    @MainActor
    func perform() async throws -> some IntentResult {
        if let url = SearchInBainLuckTerm10873.destination(for: criteria.term) {
            IntentRouteHandoff10873.shared.post(url)
        }
        return .result()
    }
}
