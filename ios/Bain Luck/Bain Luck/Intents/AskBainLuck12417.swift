import AppIntents
import Foundation

/// #12417 — Siri as an extension of search (Alex, Wed Nov 11). "Ask Bain Luck",
/// then the reader says what they want in their own words ("the Celtics
/// tonight", "will the Patriots win this weekend"). The words go to the app's
/// own search, the request the Search tab makes, and the server's answer is
/// read exactly as "Get Probability" reads it (`SearchAnswerPlan12417`):
///
/// - an exact game, outcome or market answers at once, through the same answer
///   "Get Probability" gives (a market with several outcomes asks which);
/// - anything else offers the top few rows to pick from, best guess first and
///   never spoken as the answer;
/// - nothing found says so, in the reader's words.
///
/// Apple lets a phrase hold no free text, so the words are the intent's one
/// asked-for value. The only thing the app does to them is drop the spoken
/// framing around a name (`SpokenRequest12417`); which game or market it is
/// stays the server's call.
struct AskBainLuckIntent12417: AppIntent {
    static let title: LocalizedStringResource = "Ask Bain Luck"
    static let description = IntentDescription(
        "Say a team, game or market in your own words. Bain Luck searches for it the way the Search tab does and says the chance it shows.")

    @Parameter(title: "Request", requestValueDialog: "What do you want to know?")
    var request: String

    /// Set only by "Which one?", when the search answer is a list.
    @Parameter(title: "Game or Market")
    var pick: GameOrMarketEntity10873?

    /// Set only by "Which outcome?", for a market with several outcomes.
    @Parameter(title: "Outcome")
    var outcome: OutcomeEntity10873?

    static var parameterSummary: some ParameterSummary {
        Summary("Ask Bain Luck about \(\.$request)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let text = try await answerText(now: Date())
        return .result(value: text, dialog: IntentDialog("\(text)"))
    }

    @MainActor
    private func answerText(now: Date) async throws -> String {
        let queries = SpokenRequest12417.queries(from: request)
        guard let first = queries.first else { return SpokenRequest12417.emptyReply }
        var plan = SearchAnswerPlan12417.list([])
        for query in queries {
            let response: SearchResponse
            do {
                response = try await IntentReadDeadline10873.run { try await APIClient.shared.fetchSearch(query: query) }
            } catch {
                return ProbabilityAnswer10873.failure(error, subject: "“\(first)”").text
            }
            plan = SearchAnswerPlan12417.plan(for: response)
            if !plan.entities.isEmpty { break }
        }
        let subject: GameOrMarketEntity10873
        switch AskChoice12417.decide(plan) {
        case .none:
            return SpokenRequest12417.notFoundReply(first)
        case .answer(let entity):
            subject = entity
        case .ask(let options):
            subject = try await $pick.requestDisambiguation(among: options, dialog: "Which one?")
        }
        let outcomeParameter = $outcome
        return try await GetProbabilityIntent10873.answer(subject: subject, outcome: outcome, now: now) { options, dialog in
            try await outcomeParameter.requestDisambiguation(among: options, dialog: dialog)
        }.text
    }
}

/// What "Ask Bain Luck" does with one search answer, as plain values.
nonisolated enum AskChoice12417 {
    case none
    case answer(GameOrMarketEntity10873)
    case ask([GameOrMarketEntity10873])

    /// "Which one?" reads its rows aloud, so it offers a handful, not a page.
    static let askLimit = 5

    static func decide(_ plan: SearchAnswerPlan12417) -> Self {
        switch plan {
        case .game(let entity), .outcome(let entity), .market(let entity):
            return .answer(entity)
        case .set(let entities), .list(let entities):
            let options = Array(entities.prefix(askLimit))
            switch options.count {
            case 0: return .none
            case 1: return .answer(options[0])
            default: return .ask(options)
            }
        }
    }
}

/// The spoken framing around a name, dropped before the words reach search.
///
/// Measured against live search on Wed Nov 11 (7 AM PT): "the celtics" and
/// "celtics tonight" find the Celtics' games, but "will the patriots win this
/// weekend", "chances the lakers win", "who is favored in the kentucky governor
/// race" and "celtics game" find nothing. So the words go first with only the
/// framing ahead of the name removed, and once more with the trailing
/// "win / game / race / tonight / this weekend" removed if the first finds
/// nothing. Two searches at most; which result it is stays search's call.
nonisolated enum SpokenRequest12417 {
    static let emptyReply = "Say a team, a game or a market, and Bain Luck will look it up."

    static func notFoundReply(_ query: String) -> String {
        "Bain Luck didn't find a game or market for “\(query)”."
    }

    /// Longest first, so "what are the chances of" is taken whole.
    static let leadingFraming = [
        "what does bain luck say about", "what does bain luck say", "what do you say about",
        "what are the chances that", "what are the chances of", "what are the chances",
        "what are the odds that", "what are the odds of", "what are the odds",
        "what's the chance that", "what's the chance of", "what is the chance that", "what is the chance of",
        "who's favored to win", "who is favored to win", "who's favored in", "who is favored in",
        "who's favored", "who is favored", "who will win", "who wins",
        "tell me about", "how about", "what about", "how are", "how is",
        "chances that", "chances of", "chance that", "chance of", "odds that", "odds of",
        "chances", "odds", "about", "will", "can", "do", "does", "is", "are", "the",
    ]

    /// Dropped from the end only on the second try.
    static let trailingFraming = [
        "this weekend", "this week", "tonight", "today", "tomorrow",
        "winning", "wins", "win", "game", "match", "race", "chances", "odds",
    ]

    /// The searches to try, in order: one or two, never empty strings.
    static func queries(from spoken: String) -> [String] {
        let first = strip(leading: normalized(spoken))
        guard !first.isEmpty else { return [] }
        let second = strip(trailing: first)
        return second.isEmpty || second == first ? [first] : [first, second]
    }

    static func normalized(_ text: String) -> String {
        let lowered = text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "?!.,")))
        return lowered.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    static func strip(leading text: String) -> String {
        var words = text
        var changed = true
        while changed {
            changed = false
            for phrase in leadingFraming where words == phrase || words.hasPrefix(phrase + " ") {
                words = String(words.dropFirst(phrase.count)).trimmingCharacters(in: .whitespaces)
                changed = true
                break
            }
        }
        return words
    }

    static func strip(trailing text: String) -> String {
        var words = text
        var changed = true
        while changed {
            changed = false
            for phrase in trailingFraming where words.hasSuffix(" " + phrase) {
                words = String(words.dropLast(phrase.count)).trimmingCharacters(in: .whitespaces)
                changed = true
                break
            }
        }
        return words
    }
}
