import AppIntents
import Foundation

// #10873 — the three actions of the first release: Open My Stuff, Open a game or
// market, Get probability. Native owns delivery; these are the source.
//
// The two OPEN actions bring the app forward and hand `IntentRouteHandoff10873`
// the same canonical link a widget or shared URL would carry, so they land
// exactly where that link lands and go through the app's one router. GET
// PROBABILITY answers without opening the app and reads only public data, so
// it works signed out. No action reads saved pins: private state stays on the
// My Stuff screen, which shows the signed-in reader's own content or asks them
// to sign in.

struct OpenMyStuffIntent10873: AppIntent {
    static let title: LocalizedStringResource = "Open My Stuff"
    static let description = IntentDescription(
        "Opens My Stuff in Bain Luck. If you're signed out, My Stuff asks you to sign in.")
    static let openAppWhenRun: Bool = true

    @available(iOS 26.0, macOS 26.0, visionOS 26.0, *)
    static var supportedModes: IntentModes { .foreground }

    @MainActor
    func perform() async throws -> some IntentResult {
        IntentRouteHandoff10873.shared.post(IntentLinks10873.myStuff)
        return .result()
    }
}

struct OpenGameOrMarketIntent10873: AppIntent {
    static let title: LocalizedStringResource = "Open Game or Market"
    static let description = IntentDescription(
        "Opens a game or market in Bain Luck. If more than one matches, you choose which.")
    static let openAppWhenRun: Bool = true

    @available(iOS 26.0, macOS 26.0, visionOS 26.0, *)
    static var supportedModes: IntentModes { .foreground }

    @Parameter(title: "Game or Market", requestValueDialog: "Which game or market?")
    var subject: GameOrMarketEntity10873

    static var parameterSummary: some ParameterSummary {
        Summary("Open \(\.$subject)")
    }

    @MainActor
    func perform() async throws -> some IntentResult {
        // `perform` runs only once `subject` has resolved, so a reader who backs
        // out of "Which one?" never reaches this line and nothing is opened.
        guard let link = subject.link, IntentRouteHandoff10873.shared.post(link) else {
            throw IntentFailure10873.cannotOpen
        }
        return .result()
    }
}

struct GetProbabilityIntent10873: AppIntent {
    static let title: LocalizedStringResource = "Get Probability"
    static let description = IntentDescription(
        "Says the chance Bain Luck shows for one team or outcome, and when it was recorded. A settled game or market answers with its result.")

    @Parameter(title: "Game or Market", requestValueDialog: "Which game or market?")
    var subject: GameOrMarketEntity10873

    /// Optional so a one-outcome market answers without a second question. Any
    /// game, and any market with more than one outcome, asks; nothing is picked
    /// for the reader.
    @Parameter(title: "Outcome")
    var outcome: OutcomeEntity10873?

    static var parameterSummary: some ParameterSummary {
        Summary("Get the chance for \(\.$outcome) in \(\.$subject)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let answer = try await answer(now: Date())
        return .result(value: answer.text, dialog: IntentDialog("\(answer.text)"))
    }

    /// One read of the detail feeds both the outcome list and the answer, so the
    /// reader chooses among exactly the outcomes the answer is computed from.
    @MainActor
    private func answer(now: Date) async throws -> ProbabilityAnswer10873 {
        switch subject.kind {
        case .game:
            let event: EventDetail
            do {
                event = try await APIClient.shared.fetchEvent(id: subject.recordID)
            } catch {
                return ProbabilityAnswer10873.failure(error, subject: subject.title)
            }
            let chosen = try await choose(
                from: OutcomeEntity10873.options(for: event), dialog: "Which team?")
            guard let chosen, let side = GameSide10873(rawValue: chosen.key) else {
                return ProbabilityAnswer10873(
                    kind: .unavailable,
                    text: "Bain Luck has no teams listed for \(subject.title).",
                    figure: nil)
            }
            return ProbabilityAnswer10873.game(event, side: side, now: now)
        case .market:
            let market: FuturesMarketDetail
            do {
                market = try await APIClient.shared.fetchFuturesDetail(
                    id: subject.recordID, representation: .verifiedTitle)
            } catch {
                return ProbabilityAnswer10873.failure(error, subject: subject.title)
            }
            let chosen = try await choose(
                from: OutcomeEntity10873.options(for: market), dialog: "Which outcome?")
            guard let chosen, let outcomeID = Int(chosen.key) else {
                return ProbabilityAnswer10873(
                    kind: .unavailable,
                    text: "\(market.name) has no outcomes listed right now.",
                    figure: nil)
            }
            return ProbabilityAnswer10873.market(market, outcomeID: outcomeID, now: now)
        }
    }

    /// The outcome to answer for. A supplied outcome counts only if it belongs to
    /// THIS subject (its identifier carries the subject's); otherwise, and when
    /// none was supplied, the reader picks. Only a lone outcome is taken unasked.
    @MainActor
    private func choose(from options: [OutcomeEntity10873], dialog: IntentDialog) async throws -> OutcomeEntity10873? {
        if let outcome, let match = OutcomeChoice10873.supplied(outcome.id, among: options) {
            return match
        }
        switch OutcomeChoice10873.decide(optionCount: options.count) {
        case .none: return nil
        case .only: return options[0]
        case .ask: return try await $outcome.requestDisambiguation(among: options, dialog: dialog)
        }
    }
}

/// The outcome rule as plain values, so it is testable without a Siri session.
nonisolated enum OutcomeChoice10873: Equatable, Sendable {
    case none
    case only
    case ask

    static func decide(optionCount: Int) -> Self {
        switch optionCount {
        case 0: return .none
        case 1: return .only
        default: return .ask
        }
    }

    /// The supplied outcome, if it is one of these options; nil otherwise.
    static func supplied(_ identifier: String, among options: [OutcomeEntity10873]) -> OutcomeEntity10873? {
        options.first { $0.id == identifier }
    }
}

nonisolated enum IntentFailure10873: Error, CustomLocalizedStringResourceConvertible {
    case cannotOpen

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .cannotOpen: return "Bain Luck couldn't open that."
        }
    }
}

/// The phrases Siri listens for. Every phrase names the app, as Apple requires.
/// Registering them promises these phrases and these Shortcuts actions — not
/// free-form questions.
nonisolated struct BainLuckShortcuts10873: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: GetProbabilityIntent10873(),
            phrases: [
                "Get a probability from \(.applicationName)",
                "Ask \(.applicationName) for a chance",
                "Check a chance in \(.applicationName)",
            ],
            shortTitle: "Get Probability",
            systemImageName: "percent"
        )
        AppShortcut(
            intent: OpenGameOrMarketIntent10873(),
            phrases: [
                "Open a game in \(.applicationName)",
                "Open a market in \(.applicationName)",
                "Find a game in \(.applicationName)",
            ],
            shortTitle: "Open Game or Market",
            systemImageName: "magnifyingglass"
        )
        AppShortcut(
            intent: OpenMyStuffIntent10873(),
            phrases: [
                "Open My Stuff in \(.applicationName)",
                "Show My Stuff in \(.applicationName)",
                "Show my saved markets in \(.applicationName)",
            ],
            shortTitle: "My Stuff",
            systemImageName: "person.fill"
        )
    }
}
