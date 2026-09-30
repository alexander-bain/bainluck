import Foundation

protocol ContainerHubLoading: Sendable {
    nonisolated func load(slug: String) async throws -> ContainerHubResponse
}

/// Uses the shared API transport/auth/error handling. No discovery URL is
/// invented: #9653 is a producer awaiting its surface owner's placement.
nonisolated struct ContainerHubService: ContainerHubLoading {
    let client: APIClient

    init(client: APIClient = .shared) { self.client = client }

    func load(slug: String) async throws -> ContainerHubResponse {
        try await client.fetchContainerHub(slug: slug)
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
