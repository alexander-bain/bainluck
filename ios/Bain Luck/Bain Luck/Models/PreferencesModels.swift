import Foundation

// MARK: - GET /api/me/preferences Response

nonisolated struct PreferencesResponse: Decodable, Sendable {
    let homeLocation: String?
    let sportAffinities: [String: Double]
    let onboardingCompleted: Bool
    let favorites: [FavoriteItem]
}

nonisolated struct FavoriteItem: Decodable, Identifiable, Sendable {
    let teamId: Int
    let teamName: String
    let relationType: String       // "follow", "local", "alma_mater", "rival"
    let sportKey: String?
    let logoUrl: String?
    let source: String?
    var id: Int { teamId }
}

// MARK: - POST /api/me/favorites Body

nonisolated struct AddFavoriteRequest: Encodable, Sendable {
    let teamId: Int
    let relationType: String
}

// MARK: - PUT /api/me/preferences/sport-affinities Body

nonisolated struct SportAffinitiesUpdate: Encodable, Sendable {
    let sportAffinities: [String: Double]
}

// MARK: - Generic Status Response

nonisolated struct StatusResponse: Decodable, Sendable {
    let status: String
}
