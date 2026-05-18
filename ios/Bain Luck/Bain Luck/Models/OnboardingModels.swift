import Foundation

// MARK: - Team Search Response

/// Sport-specific variant for a team returned during onboarding search.
nonisolated struct TeamSportVariant: Decodable, Identifiable, Sendable {
    let id: Int
    let sportKey: String?
    let sportDisplay: String?
}

/// Response item from GET /api/me/teams/by-location and /api/me/teams/search
nonisolated struct TeamSearchResult: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let location: String?
    let sportKey: String?
    let logoUrl: String?
    let abbreviation: String?
    let sports: [TeamSportVariant]?
}

// MARK: - Selected Team (local UI state)

/// Local selection state for a team chosen during onboarding.
nonisolated struct SelectedTeam: Identifiable, Sendable {
    let id: Int
    let name: String
    let sportKey: String?
    let logoUrl: String?
    var selected: Bool
}

// MARK: - Onboarding Submission

/// Encodable reference to a team included in onboarding preferences.
nonisolated struct TeamRef: Encodable, Sendable {
    let teamId: Int
}

/// Payload that saves a user's onboarding location, teams, and sport affinities.
nonisolated struct OnboardingSubmission: Encodable, Sendable {
    let homeLocation: String?
    let localTeams: [TeamRef]
    let followTeams: [TeamRef]
    let almaMaterTeams: [TeamRef]
    let rivalTeams: [TeamRef]
    let sportAffinities: [String: Double]
    let rawInputs: [String: [String]]
}

/// Backend status returned after onboarding preferences are saved.
nonisolated struct OnboardingResponse: Decodable, Sendable {
    let status: String
    let onboardingCompleted: Bool
}

// MARK: - Affinity Levels

/// Discrete preference levels used to convert onboarding choices into affinity weights.
enum AffinityLevel: Double, CaseIterable, Sendable {
    case loveIt = 1.0
    case bigMoments = 0.3
    case ifWild = 0.1
    case nah = 0.0

    var label: String {
        switch self {
        case .loveIt: "Love it"
        case .bigMoments: "Big moments"
        case .ifWild: "If wild"
        case .nah: "Nah"
        }
    }

    var shortLabel: String {
        switch self {
        case .loveIt: "Love"
        case .bigMoments: "Big"
        case .ifWild: "Wild"
        case .nah: "Nah"
        }
    }
}

// MARK: - Sport / Category Grid Data

/// Display metadata for an onboarding sport or category preference item.
nonisolated struct SportItem: Identifiable, Sendable {
    let key: String
    let name: String
    let emoji: String
    let isDefault: Bool
    var id: String { key }
}

/// Static catalog of sports and non-sports categories shown during onboarding.
enum OnboardingSportsData {
    static let sports: [SportItem] = [
        SportItem(key: "football", name: "NFL", emoji: "\u{1F3C8}", isDefault: true),
        SportItem(key: "cfb", name: "College Football", emoji: "\u{1F3C8}", isDefault: true),
        SportItem(key: "basketball", name: "NBA", emoji: "\u{1F3C0}", isDefault: true),
        SportItem(key: "cbb", name: "College Basketball", emoji: "\u{1F3C0}", isDefault: true),
        SportItem(key: "baseball", name: "Baseball", emoji: "\u{26BE}", isDefault: true),
        SportItem(key: "hockey", name: "Hockey", emoji: "\u{1F3D2}", isDefault: false),
        SportItem(key: "mma", name: "MMA", emoji: "\u{1F94A}", isDefault: false),
        SportItem(key: "boxing", name: "Boxing", emoji: "\u{1F94A}", isDefault: false),
        SportItem(key: "golf", name: "Golf", emoji: "\u{26F3}", isDefault: false),
        SportItem(key: "tennis", name: "Tennis", emoji: "\u{1F3BE}", isDefault: false),
        SportItem(key: "soccer", name: "Soccer", emoji: "\u{26BD}", isDefault: false),
        SportItem(key: "cricket", name: "Cricket", emoji: "\u{1F3CF}", isDefault: false),
        SportItem(key: "rugby", name: "Rugby", emoji: "\u{1F3C9}", isDefault: false),
        SportItem(key: "aussierules", name: "AFL", emoji: "\u{1F3C9}", isDefault: false),
    ]

    static let beyondSports: [SportItem] = [
        SportItem(key: "politics", name: "Politics", emoji: "\u{1F5F3}", isDefault: false),
        SportItem(key: "entertainment", name: "Entertainment", emoji: "\u{1F3AC}", isDefault: false),
        SportItem(key: "crypto", name: "Crypto", emoji: "\u{20BF}", isDefault: false),
        SportItem(key: "economics", name: "Economics", emoji: "\u{1F4C8}", isDefault: false),
        SportItem(key: "tech", name: "Tech", emoji: "\u{1F4BB}", isDefault: false),
        SportItem(key: "weather", name: "Weather", emoji: "\u{1F326}", isDefault: false),
        SportItem(key: "geopolitics", name: "Geopolitics", emoji: "\u{1F30D}", isDefault: false),
        SportItem(key: "culture", name: "Culture", emoji: "\u{1F3AD}", isDefault: false),
    ]

    static var defaultAffinities: [String: Double] {
        var affinities: [String: Double] = [:]
        for item in sports {
            affinities[item.key] = item.isDefault ? 1.0 : 0.0
        }
        for item in beyondSports {
            affinities[item.key] = 0.0
        }
        return affinities
    }
}
