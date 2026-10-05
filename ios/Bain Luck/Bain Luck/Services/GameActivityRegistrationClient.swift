#if os(iOS)
import Foundation

nonisolated struct GameActivityRegistrationMetadata: Codable, Sendable {
    let activityID: String
    let eventID: Int
    let version: Int
    let isActive: Bool
    enum CodingKeys: String, CodingKey {
        case activityID = "activity_id", eventID = "event_id", version
        case isActive = "is_active"
    }
}

nonisolated enum GameActivityRegistrationError: Error {
    case conflict, unavailable, invalidResponse
}

@MainActor protocol GameActivityRegistrationTransport {
    func read(id: String, bearer: String) async throws -> GameActivityRegistrationMetadata
    func mutate(id: String, eventID: Int, token: String?, version: Int,
                mutationID: UUID, bearer: String) async throws -> GameActivityRegistrationMetadata
}

/// Uses the existing backend session credential. No token or response body is logged.
@MainActor final class GameActivityRegistrationClient: GameActivityRegistrationTransport {
    private let session: URLSession
    private let baseURL: URL
    init(session: URLSession? = nil,
         baseURL: URL = URL(string: "https://api.bainluck.com")!) {
        if let session { self.session = session }
        else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 8
            configuration.timeoutIntervalForResource = 12
            self.session = URLSession(configuration: configuration)
        }
        self.baseURL = baseURL
    }
    func read(id: String, bearer: String) async throws -> GameActivityRegistrationMetadata {
        try await send(id: id, method: "GET", body: nil, bearer: bearer)
    }
    func mutate(id: String, eventID: Int, token: String?, version: Int,
                mutationID: UUID, bearer: String) async throws -> GameActivityRegistrationMetadata {
        var body: [String: Any] = ["event_id": eventID, "expected_version": version,
                                   "mutation_id": mutationID.uuidString]
        if let token { body["push_token"] = token }
        return try await send(id: id, method: token == nil ? "DELETE" : "PUT",
                              body: JSONSerialization.data(withJSONObject: body), bearer: bearer)
    }
    private func send(id: String, method: String, body: Data?, bearer: String) async throws
        -> GameActivityRegistrationMetadata {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        guard !bearer.isEmpty, !id.isEmpty, id.count <= 128,
              id.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw GameActivityRegistrationError.invalidResponse
        }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/activitykit/registrations")
            .appendingPathComponent(id), timeoutInterval: 8)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else {
                throw GameActivityRegistrationError.invalidResponse
            }
            if response.statusCode == 409 { throw GameActivityRegistrationError.conflict }
            guard response.statusCode == 200 else { throw GameActivityRegistrationError.unavailable }
            let metadata = try JSONDecoder().decode(GameActivityRegistrationMetadata.self, from: data)
            guard metadata.activityID == id, metadata.eventID > 0, metadata.version > 0 else {
                throw GameActivityRegistrationError.invalidResponse
            }
            return metadata
        } catch let error as GameActivityRegistrationError { throw error }
        catch { throw GameActivityRegistrationError.unavailable }
    }
}
#endif
