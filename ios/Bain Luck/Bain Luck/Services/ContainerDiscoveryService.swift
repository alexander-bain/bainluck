import Foundation

nonisolated protocol ContainerDiscoveryLoading: Sendable {
    nonisolated func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse
}

nonisolated struct ContainerDiscoveryService: ContainerDiscoveryLoading {
    let client: APIClient
    init(client: APIClient = .shared) { self.client = client }

    func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse {
        try await client.fetchContainerDiscovery(request)
    }
}
