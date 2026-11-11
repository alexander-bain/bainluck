import Foundation

/// #10873 — the rows "Which game or market?" offers before the reader says
/// anything: the top answer the app's own search gives to each of today's
/// trending searches, in trending order, each game or market once. It is the
/// Search tab's empty state (trending searches) answered the way the Search tab
/// answers them, so Siri and Spotlight stay an extension of search (Alex, Nov 11).
///
/// Public data only, never the reader's pins or recent searches. Every read is
/// bounded (`IntentReadDeadline10873`); a search that fails or times out drops
/// its row, and a failed trending read offers nothing, as before.
nonisolated enum TrendingSuggestions10873 {
    /// Enough to choose from in a prompt, few enough to read aloud.
    static let limit = 5

    static func entities(
        trending: @escaping @Sendable () async throws -> [String] = {
            try await APIClient.shared.fetchTrendingSearches().trending.map(\.query)
        },
        search: @escaping @Sendable (String) async throws -> SearchResponse = {
            try await APIClient.shared.fetchSearch(query: $0)
        }
    ) async -> [GameOrMarketEntity10873] {
        guard let queries = try? await IntentReadDeadline10873.run(trending) else { return [] }
        let asked = Array(queries.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.prefix(limit))
        let answers = await withTaskGroup(of: (Int, GameOrMarketEntity10873?).self) { group in
            for (index, query) in asked.enumerated() {
                group.addTask {
                    let response = try? await IntentReadDeadline10873.run { try await search(query) }
                    return (index, response.flatMap { GameOrMarketCatalog10873.entities(from: $0).first })
                }
            }
            var collected: [(Int, GameOrMarketEntity10873?)] = []
            for await answer in group { collected.append(answer) }
            return collected
        }
        return ordered(answers)
    }

    /// Trending order, each record once, rows with no answer dropped.
    static func ordered(_ answers: [(Int, GameOrMarketEntity10873?)]) -> [GameOrMarketEntity10873] {
        var seen = Set<String>()
        return answers.sorted { $0.0 < $1.0 }.compactMap(\.1).filter { seen.insert($0.id).inserted }
    }
}
