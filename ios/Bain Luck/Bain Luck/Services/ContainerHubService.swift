import Foundation

nonisolated protocol ContainerHubLoading: Sendable {
    nonisolated func load(slug: String) async throws -> ContainerHubResponse
    nonisolated func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse
}

extension ContainerHubLoading {
    func loadPage(slug: String, cursor: String, revision: Int, limit: Int) async throws -> ContainerHubResponse {
        // Existing sports-only test/loaders remain compatible; no invented page.
        throw APIError.invalidURL
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

    static func path(for slug: String) throws -> String {
        guard !slug.isEmpty, slug.count <= 200, slug != ".", slug != "..",
              !slug.contains("/"), !slug.contains("?"), !slug.contains("#"),
              let component = slug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#%"))) else {
            throw APIError.invalidURL
        }
        return "/api/containers/\(component)"
    }
}
