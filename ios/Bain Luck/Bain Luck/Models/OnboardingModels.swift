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
///
/// `key` is what the app **writes** — it must be a key
/// `_expand_sport_affinities` knows (`SPORT_AFFINITY_MAPPING`,
/// `backend/app/routes/user.py`), or the tap is stored verbatim and nothing
/// ever reads it. `servedKeys` are the compressed categories
/// `GET /api/me/preferences` can hand back for this tile
/// (`_compress_sport_affinities`); for all but Golf that is the write key
/// itself. The two vocabularies are NOT the same — reading a tile with its
/// write key is the #6671 defect.
nonisolated struct SportItem: Identifiable, Sendable {
    let key: String
    let name: String
    let emoji: String
    let isDefault: Bool
    let servedKeys: [String]

    init(key: String, name: String, emoji: String, isDefault: Bool, servedKeys: [String]? = nil) {
        self.key = key
        self.name = name
        self.emoji = emoji
        self.isDefault = isDefault
        self.servedKeys = servedKeys ?? [key]
    }

    var id: String { key }
}

/// Static catalog of sports and non-sports categories shown during onboarding.
enum OnboardingSportsData {
    static let sports: [SportItem] = [
        SportItem(key: "nfl", name: "NFL", emoji: "\u{1F3C8}", isDefault: true),
        SportItem(key: "college_football", name: "College Football", emoji: "\u{1F3C8}", isDefault: true),
        SportItem(key: "nba", name: "NBA", emoji: "\u{1F3C0}", isDefault: true),
        SportItem(key: "college_basketball", name: "College Basketball", emoji: "\u{1F3C0}", isDefault: true),
        SportItem(key: "baseball", name: "Baseball", emoji: "\u{26BE}", isDefault: true),
        SportItem(key: "hockey", name: "Hockey", emoji: "\u{1F3D2}", isDefault: false),
        SportItem(key: "mma", name: "MMA", emoji: "\u{1F94A}", isDefault: false),
        SportItem(key: "boxing", name: "Boxing", emoji: "\u{1F94A}", isDefault: false),
        // One tile, four served tours. `golf` is the legacy write key and is the
        // only one that expands to all of them, so the tile writes it and reads
        // the max of what comes back.
        SportItem(key: "golf", name: "Golf", emoji: "\u{26F3}", isDefault: false,
                  servedKeys: ["golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"]),
        SportItem(key: "tennis", name: "Tennis", emoji: "\u{1F3BE}", isDefault: false),
        SportItem(key: "soccer", name: "Soccer", emoji: "\u{26BD}", isDefault: false),
        SportItem(key: "cricket", name: "Cricket", emoji: "\u{1F3CF}", isDefault: false),
        SportItem(key: "rugby", name: "Rugby", emoji: "\u{1F3C9}", isDefault: false),
        // #6671: `aussierules` is NOT in SPORT_AFFINITY_MAPPING, so this tap is
        // stored verbatim, compresses away, and never comes back — the tile
        // always reads "Nah". iOS cannot fix that alone; the server needs
        // `"aussierules": ["aussierules_afl", "aussierules_other"]` (both keys
        // already exist in `sport_keys.py`). Tracked in #6671; do not delete the
        // tile to make the grid look consistent.
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

    static var allItems: [SportItem] { sports + beyondSports }

    /// Every key this catalog is authoritative for: the write keys plus every
    /// served key they read. A save clears these out of the stored payload
    /// before writing the tiles back, so one tile can never travel twice under
    /// two spellings.
    static let ownedKeys: Set<String> = Set(allItems.flatMap { [$0.key] + $0.servedKeys })

    /// Translates a served preferences payload into tile-keyed values.
    ///
    /// A tile whose served keys are all absent stays absent, which the grid
    /// renders as "Nah" — that is what an unset preference means. Golf takes
    /// the max across its four tours.
    static func tileAffinities(fromServed served: [String: Double]) -> [String: Double] {
        var affinities: [String: Double] = [:]
        for item in allItems {
            if let best = item.servedKeys.compactMap({ served[$0] }).max() {
                affinities[item.key] = best
            }
        }
        return affinities
    }

    /// Builds the body for `PUT /api/me/sport-affinities`.
    ///
    /// The tiles the reader can see, laid over any stored category this build
    /// has no tile for (`motorsport`, `esports`) — the PUT replaces rather than
    /// merges, so passing those through is the only thing stopping a tap here
    /// from erasing a preference set on the web.
    static func savePayload(
        tiles: [String: Double],
        preserving served: [String: Double]
    ) -> [String: Double] {
        var payload = served.filter { !ownedKeys.contains($0.key) }
        for (key, value) in tiles {
            payload[key] = value
        }
        return payload
    }

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
