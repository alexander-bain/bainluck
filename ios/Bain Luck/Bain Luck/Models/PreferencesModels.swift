import Foundation

// MARK: - GET /api/me/preferences Response

/// User preference response with affinities, onboarding state, and favorites.
nonisolated struct PreferencesResponse: Decodable, Sendable {
    let homeLocation: String?
    let sportAffinities: [String: Double]
    let onboardingCompleted: Bool
    let favorites: [FavoriteItem]
    /// Push-notification preferences. Optional so older responses (and
    /// signed-out defaults) decode without a value rather than failing.
    var pushPreferences: PushPreferences? = nil
}

/// Push-notification preferences mirroring the backend `push_preferences` block.
///
/// `dailyChallenge`/`bigMoves` are opt-out (default `true`); `morningDigest`
/// (Queue #200 notifications v1) is opt-IN and must default to `false` so a
/// user is never silently subscribed when the server omits the field.
nonisolated struct PushPreferences: Decodable, Sendable, Equatable {
    let dailyChallenge: Bool
    let bigMoves: Bool
    let morningDigest: Bool

    init(dailyChallenge: Bool = true, bigMoves: Bool = true, morningDigest: Bool = false) {
        self.dailyChallenge = dailyChallenge
        self.bigMoves = bigMoves
        self.morningDigest = morningDigest
    }

    private enum CodingKeys: String, CodingKey {
        case dailyChallenge, bigMoves, morningDigest
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        dailyChallenge = try container.decodeIfPresent(Bool.self, forKey: .dailyChallenge) ?? true
        bigMoves = try container.decodeIfPresent(Bool.self, forKey: .bigMoves) ?? true
        morningDigest = try container.decodeIfPresent(Bool.self, forKey: .morningDigest) ?? false
    }
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

// MARK: - PATCH /api/me/preferences/push Body + Response

/// Payload for updating push-notification preferences. Only the fields set
/// here are changed server-side (the backend uses only-provided-field semantics).
nonisolated struct UpdatePushPreferencesRequest: Encodable, Sendable {
    let morningDigest: Bool
}

/// Response from `PATCH /api/me/preferences/push`, echoing the saved prefs.
nonisolated struct UpdatePushPreferencesResponse: Decodable, Sendable {
    let status: String
    let pushPreferences: PushPreferences?
}

// MARK: - Generic Status Response

/// Generic backend status response for preference mutations.
nonisolated struct StatusResponse: Decodable, Sendable {
    let status: String
}
