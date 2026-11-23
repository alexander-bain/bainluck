import Foundation

// MARK: - Ruling 359: A — Screen 2D Plain-Sentence Chips State (#11934)

/// Plain-sentence parsing contract for Screen 2D (`"Any cities, schools or subjects you care about?"`).
///
/// The server endpoint address comes from Builder B and ships dark until Fable certifies
/// its 9-point bar (`serverEndpointPath == nil`). Until then, production preserves ordinary
/// typeahead search unchanged while the app UI holds the full waiting, confirmation-chips,
/// ambiguity-disambiguation, and could-not-read fallback states (using clearly marked sample
/// data for design preview and state verification without holding the first-run pull request).
nonisolated enum FirstRunSentenceMode359A {
    /// Builder B's certified sentence endpoint (nil until certified under 359: A).
    static let serverEndpointPath: String? = nil

    /// One- or two-word entries behave strictly as ordinary search (359: A item 9).
    /// Three+ words or multi-item lists (`"Boston, Spurs, inflation"`) qualify as plain sentences.
    static func looksLikePlainSentence(_ query: String) -> Bool {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 6 else { return false }
        let words = trimmed.split { $0.isWhitespace || $0.isNewline }
        if words.count >= 3 { return true }
        if trimmed.contains(",") || trimmed.contains(";") { return true }
        return false
    }
}

/// One resolved chip returned for a plain sentence under 359: A.
///
/// - Clear names (`preselectedByDefault == true`) arrive selected and one tap removes them.
/// - Ambiguous names sharing a reading (`ambiguityGroup != nil`, e.g. `"Spurs"`) arrive as
///   two or more unselected chips (`preselectedByDefault == false`).
nonisolated struct FirstRunSentenceChip359A: Identifiable, Equatable, Sendable {
    let id: String
    let suggestion: FirstRunSuggestion212A
    let preselectedByDefault: Bool
    let ambiguityGroup: String?

    var isAmbiguous: Bool {
        ambiguityGroup != nil && !preselectedByDefault
    }
}

nonisolated struct FirstRunSentenceResponse359A: Equatable, Sendable {
    let chips: [FirstRunSentenceChip359A]
    let isSampleData: Bool
}

nonisolated enum FirstRunSentenceState359A: Equatable, Sendable {
    case idle
    case waiting
    case chips(chips: [FirstRunSentenceChip359A], selectedIds: Set<String>, isSampleData: Bool)
    case couldNotRead(message: String)
}

/// Deterministic, clearly labeled sample provider for Screen 2D (`359: A`) previews and tests
/// while Builder B's live endpoint is pending. Never executes on silent fallback in shipping builds.
nonisolated enum FirstRunSentenceSampleProvider359A {
    static let sampleBadgeText = "Sample preview \u{00B7} waiting on server address"

    static func parseSampleSentence(_ sentence: String) async throws -> FirstRunSentenceResponse359A {
        let lower = sentence.lowercased()
        var chips: [FirstRunSentenceChip359A] = []

        if lower.contains("celtics") || lower.contains("boston") {
            let celtics = FirstRunSuggestion212A(
                id: "team:100",
                name: "Boston Celtics",
                sportOrCategoryLabel: "NBA",
                contextLine: "Boston",
                logoUrl: nil,
                primaryColorHex: "#007A33",
                teamId: 100,
                sportKey: "basketball_nba",
                followedSubject: FollowedSubject295A.team(
                    slug: "100",
                    teamId: 100,
                    name: "Boston Celtics",
                    sportKey: "basketball_nba"
                ),
                affinityCategory: "basketball",
                marketId: nil,
                matchKeywords: ["Boston Celtics", "Celtics", "Boston"]
            )
            chips.append(FirstRunSentenceChip359A(
                id: celtics.id,
                suggestion: celtics,
                preselectedByDefault: true,
                ambiguityGroup: nil
            ))
        }

        if lower.contains("oscar") {
            let oscars = FirstRunSuggestion212A(
                id: "set:roundup-oscars-best-picture",
                name: "Oscars \u{00B7} Best Picture",
                sportOrCategoryLabel: "Entertainment \u{00B7} Set",
                contextLine: "Academy Awards",
                logoUrl: nil,
                primaryColorHex: "#B45309",
                teamId: nil,
                sportKey: "entertainment",
                followedSubject: FollowedSubject295A.set(
                    slug: "roundup-oscars-best-picture",
                    setKind: .container,
                    name: "Oscars · Best Picture"
                ),
                affinityCategory: "entertainment",
                marketId: nil,
                matchKeywords: ["Oscars", "Best Picture"]
            )
            chips.append(FirstRunSentenceChip359A(
                id: oscars.id,
                suggestion: oscars,
                preselectedByDefault: true,
                ambiguityGroup: nil
            ))
        }

        if lower.contains("inflation") {
            let inflation = FirstRunSuggestion212A(
                id: "fut:52756026",
                name: "Inflation in November 2026 (CPI YoY)",
                sportOrCategoryLabel: "Economics",
                contextLine: "Macro & Fed rates",
                logoUrl: nil,
                primaryColorHex: "#005CC2",
                teamId: nil,
                sportKey: "economics",
                followedSubject: nil,
                affinityCategory: "economics",
                marketId: 52756026,
                matchKeywords: ["Inflation", "CPI", "Fed"]
            )
            chips.append(FirstRunSentenceChip359A(
                id: inflation.id,
                suggestion: inflation,
                preselectedByDefault: true,
                ambiguityGroup: nil
            ))
        }

        if lower.contains("spurs") {
            let sas = FirstRunSuggestion212A(
                id: "team:spurs-nba",
                name: "San Antonio Spurs",
                sportOrCategoryLabel: "NBA",
                contextLine: "San Antonio",
                logoUrl: nil,
                primaryColorHex: "#475569",
                teamId: 109,
                sportKey: "basketball_nba",
                followedSubject: FollowedSubject295A.team(
                    slug: "109",
                    teamId: 109,
                    name: "San Antonio Spurs",
                    sportKey: "basketball_nba"
                ),
                affinityCategory: "basketball",
                marketId: nil,
                matchKeywords: ["San Antonio Spurs", "Spurs"]
            )
            let tot = FirstRunSuggestion212A(
                id: "team:spurs-epl",
                name: "Tottenham Hotspur",
                sportOrCategoryLabel: "Premier League",
                contextLine: "North London",
                logoUrl: nil,
                primaryColorHex: "#132257",
                teamId: 184,
                sportKey: "soccer_epl",
                followedSubject: FollowedSubject295A.team(
                    slug: "184",
                    teamId: 184,
                    name: "Tottenham Hotspur",
                    sportKey: "soccer_epl"
                ),
                affinityCategory: "soccer",
                marketId: nil,
                matchKeywords: ["Tottenham Hotspur", "Spurs"]
            )
            chips.append(FirstRunSentenceChip359A(
                id: sas.id,
                suggestion: sas,
                preselectedByDefault: false,
                ambiguityGroup: "Spurs"
            ))
            chips.append(FirstRunSentenceChip359A(
                id: tot.id,
                suggestion: tot,
                preselectedByDefault: false,
                ambiguityGroup: "Spurs"
            ))
        }

        return FirstRunSentenceResponse359A(chips: chips, isSampleData: true)
    }
}
