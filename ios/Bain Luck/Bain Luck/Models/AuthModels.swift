import Foundation

// MARK: - Auth User

nonisolated struct AuthUser: Codable, Sendable {
    let id: Int
    let email: String?
    let displayName: String?
    let photoUrl: String?
    let onboardingCompleted: Bool
    let createdAt: String?
}

// MARK: - Apple Auth Response

/// Response from POST /api/auth/apple
nonisolated struct AppleAuthResponse: Decodable, Sendable {
    let customToken: String?
    let idToken: String       // Backend session token (PyJWT, 8hr TTL)
    let uid: String
    let email: String?
    let name: String?
    let picture: String?
    let expiresIn: Int         // 28800 (8 hours)
    let user: AuthUser
}

// MARK: - Auth Status Response

/// Response from GET /api/auth/status
nonisolated struct AuthStatusResponse: Decodable, Sendable {
    let authConfigured: Bool
    let providers: [String]
}
