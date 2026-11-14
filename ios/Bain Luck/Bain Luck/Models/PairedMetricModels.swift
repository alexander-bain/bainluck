import Foundation

// MARK: - Paired-Metric Visual Forms (#12642 / #12577 / 168-A)

/// The two highest-graded native grouped-card looks from Look Sheet 2 (#12642).
nonisolated enum PairedVisualFormId: String, Codable, CaseIterable, Equatable, Sendable {
    case pairedBarsTop5Expandable = "paired_bars_top5_expandable"
    case podiumAndTiers = "podium_and_tiers"
}

/// Supported art slot shapes on paired-metric contender cards (#12642).
nonisolated enum PairedArtKind: String, Codable, Equatable, Sendable {
    case tmdbPoster = "tmdb_poster"
    case tmdbHeadshot = "tmdb_headshot"
    case espnTeamLogo = "espn_team_logo"
}

/// Dynamic key wrapper so `PairedMetricSet` decodes identically under both
/// `APIClient`'s `.convertFromSnakeCase` decoder and raw snake_case fixtures.
private nonisolated struct PairedCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }

    init(_ string: String) {
        self.stringValue = string
    }

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        return nil
    }
}

private extension KeyedDecodingContainer where Key == PairedCodingKey {
    nonisolated func decodeFirst<T: Decodable>(_ type: T.Type, keys: [String]) -> T? {
        for raw in keys {
            let key = PairedCodingKey(raw)
            if contains(key), (try? decodeNil(forKey: key)) != true,
               let val = try? decode(T.self, forKey: key) {
                return val
            }
        }
        return nil
    }
}

/// Per-entry visual art metadata gated through `#7461` (`resolveKidSafeVisualArt`).
nonisolated struct PairedArtAsset: Decodable, Equatable, Sendable {
    let kind: PairedArtKind
    let url: String
    let tmdbId: Int?
    let posterPath: String?
    let profilePath: String?
    let genreIds: [Int]?
    let adult: Bool
    let kidSafeVetted: Bool

    init(
        kind: PairedArtKind,
        url: String,
        tmdbId: Int? = nil,
        posterPath: String? = nil,
        profilePath: String? = nil,
        genreIds: [Int]? = nil,
        adult: Bool = false,
        kidSafeVetted: Bool = true
    ) {
        self.kind = kind
        self.url = url
        self.tmdbId = tmdbId
        self.posterPath = posterPath
        self.profilePath = profilePath
        self.genreIds = genreIds
        self.adult = adult
        self.kidSafeVetted = kidSafeVetted
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: PairedCodingKey.self)
        let rawKind = c.decodeFirst(String.self, keys: ["kind"]) ?? PairedArtKind.tmdbPoster.rawValue
        self.kind = PairedArtKind(rawValue: rawKind) ?? .tmdbPoster
        self.url = c.decodeFirst(String.self, keys: ["url"]) ?? ""
        self.tmdbId = c.decodeFirst(Int.self, keys: ["tmdbId", "tmdb_id"])
        self.posterPath = c.decodeFirst(String.self, keys: ["posterPath", "poster_path"])
        self.profilePath = c.decodeFirst(String.self, keys: ["profilePath", "profile_path"])
        self.genreIds = c.decodeFirst([Int].self, keys: ["genreIds", "genre_ids"])
        self.adult = c.decodeFirst(Bool.self, keys: ["adult"]) ?? true
        self.kidSafeVetted = c.decodeFirst(Bool.self, keys: ["kidSafeVetted", "kid_safe_vetted"]) ?? false
    }
}

/// One contender in a paired-metric grouped card (Stage 1 + Stage 2, never blended with each other).
nonisolated struct PairedSubjectEntry: Decodable, Equatable, Identifiable, Sendable {
    let subjectKey: String
    let subject: String
    let detail: String
    let stage1MarketId: Int
    let stage1Outcome: String?
    let stage1Probability: Double?
    /// `"yes"`, `"no"`, or `nil` while unsettled.
    let stage1SettledState: String?
    let stage2MarketId: Int
    let stage2Outcome: String?
    let stage2Probability: Double?
    let missingStage1Reason: String?
    let missingStage2Reason: String?
    let art: PairedArtAsset?

    var id: String { subjectKey }

    init(
        subjectKey: String,
        subject: String,
        detail: String,
        stage1MarketId: Int,
        stage1Outcome: String? = nil,
        stage1Probability: Double?,
        stage1SettledState: String? = nil,
        stage2MarketId: Int,
        stage2Outcome: String? = nil,
        stage2Probability: Double?,
        missingStage1Reason: String? = nil,
        missingStage2Reason: String? = nil,
        art: PairedArtAsset? = nil
    ) {
        self.subjectKey = subjectKey
        self.subject = subject
        self.detail = detail
        self.stage1MarketId = stage1MarketId
        self.stage1Outcome = stage1Outcome
        self.stage1Probability = stage1Probability
        self.stage1SettledState = stage1SettledState
        self.stage2MarketId = stage2MarketId
        self.stage2Outcome = stage2Outcome
        self.stage2Probability = stage2Probability
        self.missingStage1Reason = missingStage1Reason
        self.missingStage2Reason = missingStage2Reason
        self.art = art
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: PairedCodingKey.self)
        guard let subject = c.decodeFirst(String.self, keys: ["subject"]), !subject.isEmpty else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Missing paired entry subject"))
        }
        self.subject = subject
        self.subjectKey = c.decodeFirst(String.self, keys: ["subjectKey", "subject_key"]) ?? subject.lowercased()
        self.detail = c.decodeFirst(String.self, keys: ["detail"]) ?? ""
        self.stage1MarketId = c.decodeFirst(Int.self, keys: ["stage1MarketId", "stage_1_market_id"]) ?? 0
        self.stage1Outcome = c.decodeFirst(String.self, keys: ["stage1Outcome", "stage_1_outcome"])
        self.stage1Probability = c.decodeFirst(Double.self, keys: ["stage1Probability", "stage_1_probability"])
        self.stage1SettledState = c.decodeFirst(String.self, keys: ["stage1SettledState", "stage_1_settled_state"])
        self.stage2MarketId = c.decodeFirst(Int.self, keys: ["stage2MarketId", "stage_2_market_id"]) ?? 0
        self.stage2Outcome = c.decodeFirst(String.self, keys: ["stage2Outcome", "stage_2_outcome"])
        self.stage2Probability = c.decodeFirst(Double.self, keys: ["stage2Probability", "stage_2_probability"])
        self.missingStage1Reason = c.decodeFirst(String.self, keys: ["missingStage1Reason", "missing_stage_1_reason"])
        self.missingStage2Reason = c.decodeFirst(String.self, keys: ["missingStage2Reason", "missing_stage_2_reason"])
        self.art = c.decodeFirst(PairedArtAsset.self, keys: ["art"])
    }
}

/// Complete paired-metric grouped card payload (#12642 / #12577).
nonisolated struct PairedMetricSet: Decodable, Equatable, Identifiable, Sendable {
    let setId: String
    let category: String
    let kicker: String
    let title: String
    let subtitle: String
    let stage1Label: String
    let stage2Label: String
    let stage1SettledYesLabel: String
    let stage1SettledNoLabel: String
    let entries: [PairedSubjectEntry]
    let preferredVisualForm: String?

    var id: String { setId }

    var usesTMDBArt: Bool {
        entries.contains { entry in
            guard let kind = entry.art?.kind else { return false }
            return kind == .tmdbPoster || kind == .tmdbHeadshot
        }
    }

    init(
        setId: String,
        category: String,
        kicker: String,
        title: String,
        subtitle: String,
        stage1Label: String,
        stage2Label: String,
        stage1SettledYesLabel: String,
        stage1SettledNoLabel: String,
        entries: [PairedSubjectEntry],
        preferredVisualForm: String? = nil
    ) {
        self.setId = setId
        self.category = category
        self.kicker = kicker
        self.title = title
        self.subtitle = subtitle
        self.stage1Label = stage1Label
        self.stage2Label = stage2Label
        self.stage1SettledYesLabel = stage1SettledYesLabel
        self.stage1SettledNoLabel = stage1SettledNoLabel
        self.entries = entries
        self.preferredVisualForm = preferredVisualForm
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: PairedCodingKey.self)
        guard let setId = c.decodeFirst(String.self, keys: ["setId", "set_id"]), !setId.isEmpty,
              let title = c.decodeFirst(String.self, keys: ["title"]), !title.isEmpty else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Missing set_id or title on PairedMetricSet"))
        }
        self.setId = setId
        self.category = c.decodeFirst(String.self, keys: ["category"]) ?? "entertainment"
        self.kicker = c.decodeFirst(String.self, keys: ["kicker"]) ?? ""
        self.title = title
        self.subtitle = c.decodeFirst(String.self, keys: ["subtitle"]) ?? ""
        self.stage1Label = c.decodeFirst(String.self, keys: ["stage1Label", "stage_1_label"]) ?? "Qualified"
        self.stage2Label = c.decodeFirst(String.self, keys: ["stage2Label", "stage_2_label"]) ?? "Wins"
        self.stage1SettledYesLabel = c.decodeFirst(String.self, keys: ["stage1SettledYesLabel", "stage_1_settled_yes_label"]) ?? self.stage1Label
        self.stage1SettledNoLabel = c.decodeFirst(String.self, keys: ["stage1SettledNoLabel", "stage_1_settled_no_label"]) ?? "Eliminated"
        self.entries = c.decodeFirst([PairedSubjectEntry].self, keys: ["entries"]) ?? []
        self.preferredVisualForm = c.decodeFirst(String.self, keys: ["visualForm", "visual_form", "preferredVisualForm", "preferred_visual_form"])
    }
}
