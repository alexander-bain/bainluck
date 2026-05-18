import Foundation

// MARK: - GET /api/me/preferences Response

/// User preference response with affinities, onboarding state, and favorites.
nonisolated struct PreferencesResponse: Decodable, Sendable {
    let homeLocation: String?
    let sportAffinities: [String: Double]
    let onboardingCompleted: Bool
    let favorites: [FavoriteItem]
}

/// Favorite team entry saved in user preferences.
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

/// Payload for adding a team favorite with a relation type.
nonisolated struct AddFavoriteRequest: Encodable, Sendable {
    let teamId: Int
    let relationType: String
}

// MARK: - PUT /api/me/preferences/sport-affinities Body

/// Payload for updating sport and category affinity weights.
nonisolated struct SportAffinitiesUpdate: Encodable, Sendable {
    let sportAffinities: [String: Double]
}

// MARK: - Generic Status Response

/// Generic backend status response for preference mutations.
nonisolated struct StatusResponse: Decodable, Sendable {
    let status: String
}
