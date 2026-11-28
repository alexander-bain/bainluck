#if os(iOS)
import Foundation

/// Wire body for `PUT /api/devices/{device_id}` (`backend/app/routes/devices.py` `DeviceState`,
/// `extra="forbid"`). Exact snake_case keys, no extra fields.
nonisolated struct PushDeviceState254A: Equatable, Sendable, Encodable {
    static let maxPinsPerKind = 25

    let platform: String
    let apnsEnv: String
    let notificationToken: String?
    let laStartToken: String?
    let osMajor: Int
    let appVersion: String?
    let pinnedEventIDs: [Int]
    let pinnedMarketIDs: [Int]

    enum CodingKeys: String, CodingKey {
        case platform
        case apnsEnv = "apns_env"
        case notificationToken = "notification_token"
        case laStartToken = "la_start_token"
        case osMajor = "os_major"
        case appVersion = "app_version"
        case pinnedEventIDs = "pinned_event_ids"
        case pinnedMarketIDs = "pinned_market_ids"
    }

    init(
        platform: String = "ios",
        apnsEnv: String = Self.defaultAPNsEnvironment,
        notificationToken: String? = nil,
        laStartToken: String?,
        osMajor: Int = ProcessInfo.processInfo.operatingSystemVersion.majorVersion,
        appVersion: String? = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
        pinnedEventIDs: [Int],
        pinnedMarketIDs: [Int]
    ) {
        self.platform = platform
        self.apnsEnv = apnsEnv
        self.notificationToken = notificationToken?.lowercased()
        self.laStartToken = laStartToken?.lowercased()
        self.osMajor = max(0, min(99, osMajor))
        self.appVersion = appVersion.map { String($0.prefix(20)) }
        self.pinnedEventIDs = Self.normalizePinIDs(pinnedEventIDs)
        self.pinnedMarketIDs = Self.normalizePinIDs(pinnedMarketIDs)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(platform, forKey: .platform)
        try container.encode(apnsEnv, forKey: .apnsEnv)
        // Encode explicit `null` when `nil` so turning "Game alerts" off clears the server token.
        try container.encode(notificationToken, forKey: .notificationToken)
        try container.encode(laStartToken, forKey: .laStartToken)
        try container.encode(osMajor, forKey: .osMajor)
        try container.encode(appVersion, forKey: .appVersion)
        try container.encode(pinnedEventIDs, forKey: .pinnedEventIDs)
        try container.encode(pinnedMarketIDs, forKey: .pinnedMarketIDs)
    }

    static var defaultAPNsEnvironment: String {
        #if DEBUG
        return "sandbox"
        #else
        return "production"
        #endif
    }

    static func hexToken(from data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    static func normalizePinIDs(_ ids: [Int]) -> [Int] {
        Array(Set(ids.filter { $0 > 0 && $0 < Int(Int32.max) })).sorted().prefix(maxPinsPerKind).map { $0 }
    }
}

nonisolated enum PushDeviceClientError254A: Error, Equatable {
    case conflict
    case unavailable
    case invalidResponse
}

@MainActor protocol PushDeviceTransport254A {
    func putDevice(identity: DeviceIdentity254A, state: PushDeviceState254A) async throws
    func claimDevice(identity: DeviceIdentity254A, bearer: String) async throws
    func readActivityRegistration(id: String, identity: DeviceIdentity254A) async throws -> GameActivityRegistrationMetadata
    func mutateActivityRegistration(
        id: String,
        eventID: Int,
        token: String?,
        version: Int,
        mutationID: UUID,
        identity: DeviceIdentity254A
    ) async throws -> GameActivityRegistrationMetadata
}

/// Ephemeral HTTP client for `/api/devices/{device_id}` and device-owned
/// `/api/activitykit/registrations/{activity_id}`. Never logs tokens, secrets, or response bodies.
@MainActor final class PushDeviceClient254A: PushDeviceTransport254A {
    private let session: URLSession
    private let baseURL: URL

    init(
        session: URLSession? = nil,
        baseURL: URL = URL(string: "https://api.bainluck.com")!
    ) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 8
            configuration.timeoutIntervalForResource = 12
            self.session = URLSession(configuration: configuration)
        }
        self.baseURL = baseURL
    }

    func putDevice(identity: DeviceIdentity254A, state: PushDeviceState254A) async throws {
        var request = URLRequest(
            url: baseURL
                .appendingPathComponent("api/devices")
                .appendingPathComponent(identity.deviceID.uuidString.lowercased()),
            timeoutInterval: 8
        )
        request.httpMethod = "PUT"
        request.setValue(identity.secret, forHTTPHeaderField: "X-Device-Secret")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.httpBody = try JSONEncoder().encode(state)

        let (_, response) = try await perform(request)
        guard (200...299).contains(response.statusCode) else {
            throw PushDeviceClientError254A.unavailable
        }
    }

    func claimDevice(identity: DeviceIdentity254A, bearer: String) async throws {
        guard !bearer.isEmpty else { throw PushDeviceClientError254A.invalidResponse }
        var request = URLRequest(
            url: baseURL
                .appendingPathComponent("api/devices")
                .appendingPathComponent(identity.deviceID.uuidString.lowercased())
                .appendingPathComponent("claim"),
            timeoutInterval: 8
        )
        request.httpMethod = "POST"
        request.setValue(identity.secret, forHTTPHeaderField: "X-Device-Secret")
        request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        request.cachePolicy = .reloadIgnoringLocalCacheData

        let (_, response) = try await perform(request)
        guard (200...299).contains(response.statusCode) else {
            throw PushDeviceClientError254A.unavailable
        }
    }

    func readActivityRegistration(
        id: String,
        identity: DeviceIdentity254A
    ) async throws -> GameActivityRegistrationMetadata {
        try await sendActivityRegistration(id: id, method: "GET", body: nil, identity: identity)
    }

    func mutateActivityRegistration(
        id: String,
        eventID: Int,
        token: String?,
        version: Int,
        mutationID: UUID,
        identity: DeviceIdentity254A
    ) async throws -> GameActivityRegistrationMetadata {
        var body: [String: Any] = [
            "event_id": eventID,
            "expected_version": version,
            "mutation_id": mutationID.uuidString,
        ]
        if let token { body["push_token"] = token }
        let encoded = try JSONSerialization.data(withJSONObject: body)
        return try await sendActivityRegistration(
            id: id,
            method: token == nil ? "DELETE" : "PUT",
            body: encoded,
            identity: identity
        )
    }

    private func sendActivityRegistration(
        id: String,
        method: String,
        body: Data?,
        identity: DeviceIdentity254A
    ) async throws -> GameActivityRegistrationMetadata {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        guard !id.isEmpty, id.count <= 128,
              id.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw PushDeviceClientError254A.invalidResponse
        }
        var request = URLRequest(
            url: baseURL
                .appendingPathComponent("api/activitykit/registrations")
                .appendingPathComponent(id),
            timeoutInterval: 8
        )
        request.httpMethod = method
        request.httpBody = body
        request.setValue(identity.deviceID.uuidString.lowercased(), forHTTPHeaderField: "X-Device-Id")
        request.setValue(identity.secret, forHTTPHeaderField: "X-Device-Secret")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.cachePolicy = .reloadIgnoringLocalCacheData

        let (data, response) = try await perform(request)
        if response.statusCode == 409 { throw PushDeviceClientError254A.conflict }
        guard response.statusCode == 200 else { throw PushDeviceClientError254A.unavailable }
        let metadata = try JSONDecoder().decode(GameActivityRegistrationMetadata.self, from: data)
        guard metadata.activityID == id, metadata.eventID > 0, metadata.version > 0 else {
            throw PushDeviceClientError254A.invalidResponse
        }
        return metadata
    }

    private func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw PushDeviceClientError254A.invalidResponse
            }
            return (data, http)
        } catch let error as PushDeviceClientError254A {
            throw error
        } catch {
            throw PushDeviceClientError254A.unavailable
        }
    }
}
#endif
