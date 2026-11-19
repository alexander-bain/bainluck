import Foundation

nonisolated protocol ContainerHubLoading: Sendable {
    nonisolated func load(slug: String) async throws -> ContainerHubResponse
    nonisolated func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse
    nonisolated func loadMarketPage(slug: String, cursor: String, revision: Int, limit: Int, nextUrl: String?) async throws -> ContainerHubResponse
    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet]
}

extension ContainerHubLoading {
    func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse {
        // Existing sports-only test/loaders remain compatible; no invented page.
        throw APIError.invalidURL
    }

    func loadMarketPage(slug: String, cursor: String, revision: Int, limit: Int, nextUrl: String? = nil) async throws -> ContainerHubResponse {
        try await loadPage(slug: slug, cursor: cursor, revision: revision, limit: limit)
    }

    func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
        []
    }
}

/// Uses the shared API transport/auth/error handling. No discovery URL is
/// invented: #9653 is a producer awaiting its surface owner's placement.
nonisolated struct ContainerHubService: ContainerHubLoading {
    let client: APIClient

    init(client: APIClient = .shared) { self.client = client }

    func load(slug: String) async throws -> ContainerHubResponse {
        try await client.fetchContainerHub(slug: slug)
    }

    func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse {
        guard revision > 0, ContainerHubPage.validCursor(cursor) else { throw APIError.invalidURL }
        return try await client.fetchContainerHub(slug: slug, cursor: cursor, revision: revision, limit: limit)
    }

    func loadMarketPage(slug: String, cursor: String, revision: Int, limit: Int, nextUrl: String? = nil) async throws -> ContainerHubResponse {
        guard revision > 0, ContainerHubPage.validMarketCursor(cursor) else { throw APIError.invalidURL }
        return try await client.fetchContainerHubMarketPage(slug: slug, cursor: cursor, revision: revision, limit: limit, nextUrl: nextUrl)
    }

    /// Builds the exact continuation path + query for deferred week markets (#12901).
    /// Prefers the server's `page.nextUrl` (which echoes `include_children` and `PAGE_DEFAULT`
    /// `market_limit`), and otherwise omits `include_children` so the continuation matches
    /// `fetchContainerHub(slug:)`'s backend default (`include_children=True`, `own=False`).
    static func marketContinuationRequest(
        slug: String,
        cursor: String,
        revision: Int,
        limit: Int,
        nextUrl: String? = nil
    ) throws -> (path: String, query: [String: String]) {
        let expectedPath = try path(for: slug)
        guard revision > 0, ContainerHubPage.validMarketCursor(cursor), (1...100).contains(limit) else {
            throw APIError.invalidURL
        }
        if let nextUrl, !nextUrl.isEmpty,
           let comps = URLComponents(string: nextUrl),
           comps.scheme == nil, comps.host == nil,
           comps.path == expectedPath,
           let items = comps.queryItems, !items.isEmpty {
            let allowedKeys: Set<String> = ["market_cursor", "market_revision", "market_limit", "include_children"]
            var q: [String: String] = [:]
            for item in items where allowedKeys.contains(item.name) {
                if let val = item.value, !val.isEmpty {
                    q[item.name] = val
                }
            }
            if let urlCursor = q["market_cursor"], ContainerHubPage.validMarketCursor(urlCursor),
               let urlRevStr = q["market_revision"], let urlRev = Int(urlRevStr), urlRev == revision {
                if let limStr = q["market_limit"], let limVal = Int(limStr), (1...100).contains(limVal) {
                    return (expectedPath, q)
                }
                q["market_limit"] = String(limit)
                return (expectedPath, q)
            }
        }
        return (
            expectedPath,
            [
                "market_cursor": cursor,
                "market_revision": String(revision),
                "market_limit": String(limit),
            ]
        )
    }

    func loadPairedMetrics(slug: String) async -> [PairedMetricSet] {
        guard slug == "oscars-2027" || slug == "oscars" || slug == "the-oscars" else {
            return []
        }
        return (try? await client.fetchPairedMetrics(ceremony: "oscars")) ?? []
    }

    static func path(for slug: String) throws -> String {
        guard !slug.isEmpty, slug.count <= 200, slug != ".", slug != "..",
              !slug.contains("/"), !slug.contains("?"), !slug.contains("#"),
              let component = slug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#%"))) else {
            throw APIError.invalidURL
        }
        return "/api/containers/\(component)"
    }
}
