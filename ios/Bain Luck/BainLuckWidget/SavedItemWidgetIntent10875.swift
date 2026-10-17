import AppIntents
import Foundation
import WidgetKit

// #10875 — how a reader chooses what one widget follows: one of THEIR saved
// games or markets (read from the app's bridge, never from a public catalog or
// feed), and, where it matters, the side or outcome to name.

// MARK: - Fetching a public detail

/// `GET /api/events/{id}` or `/api/futures/{id}?representation=verified_title`
/// — public, no credential, and the same request the detail page one tap away
/// makes (`FuturesDetailViewModel`'s default representation), so the widget
/// and the page print the same number for the same outcome.
nonisolated enum SavedItemWidgetFetch10875 {
    static let baseURL = "https://api.bainluck.com"

    static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    static func url(for subject: SavedWidgetSubject10875) -> URL? {
        switch subject.kind {
        case .game: return URL(string: "\(baseURL)/api/events/\(subject.id)")
        // An ineligible board answers in source mode, as it does for the page.
        case .market: return URL(string: "\(baseURL)/api/futures/\(subject.id)?representation=verified_title")
        }
    }

    static func data(for subject: SavedWidgetSubject10875) async throws -> Data {
        guard let url = url(for: subject) else { throw SavedWidgetFetchError10875.failed }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(from: url)
        } catch {
            throw SavedWidgetFetchError10875.failed
        }
        guard let http = response as? HTTPURLResponse else { throw SavedWidgetFetchError10875.failed }
        // 410 is a retired fixture (`routes/events.py`): gone, as the app's pin
        // surfaces read it, not a network failure to retry forever.
        if http.statusCode == 404 || http.statusCode == 410 { throw SavedWidgetFetchError10875.notFound }
        guard (200...299).contains(http.statusCode) else { throw SavedWidgetFetchError10875.failed }
        return data
    }

    static func payload(for subject: SavedWidgetSubject10875) async -> SavedWidgetDetailPayload10875? {
        guard let data = try? await data(for: subject) else { return nil }
        return try? SavedWidgetDetailPayload10875.decode(data, as: subject.kind)
    }

    static var bridge: SavedWidgetSnapshot10875? {
        SavedWidgetBridge10875.sharedDefaults.flatMap { SavedWidgetBridgeStore10875(defaults: $0).read() }
    }

    static var cache: SavedWidgetDetailCache10875 { SavedWidgetDetailCache10875(defaults: .standard) }
}

// MARK: - The saved item

struct SavedItemEntity10875: AppEntity {
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Game or market"
    static var defaultQuery = SavedItemEntityQuery10875()

    /// "<account scope>|game:123" — the scope travels with the choice.
    let id: String
    let title: String

    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(title)") }
}

struct SavedItemEntityQuery10875: EntityQuery {
    /// The current reader's saved items, titled from their public details.
    func suggestedEntities() async throws -> [SavedItemEntity10875] {
        guard let snapshot = SavedItemWidgetFetch10875.bridge else { return [] }
        return await withTaskGroup(of: (Int, SavedItemEntity10875).self) { group in
            for (index, subject) in snapshot.subjects.enumerated() {
                group.addTask {
                    (index, await Self.entity(scope: snapshot.scope, subject: subject, snapshot: snapshot))
                }
            }
            var found: [(Int, SavedItemEntity10875)] = []
            for await item in group { found.append(item) }
            return found.sorted { $0.0 < $1.0 }.map(\.1)
        }
    }

    func entities(for identifiers: [SavedItemEntity10875.ID]) async throws -> [SavedItemEntity10875] {
        let snapshot = SavedItemWidgetFetch10875.bridge
        var result: [SavedItemEntity10875] = []
        for id in identifiers {
            guard let parsed = SavedWidgetSelection10875.parse(entityID: id) else { continue }
            result.append(await Self.entity(scope: parsed.scope, subject: parsed.subject, snapshot: snapshot))
        }
        return result
    }

    /// A choice from another account is named as that and nothing more: its
    /// title would say what that account saved.
    static func entity(scope: String, subject: SavedWidgetSubject10875,
                       snapshot: SavedWidgetSnapshot10875?) async -> SavedItemEntity10875 {
        let id = SavedWidgetSelection10875.entityID(scope: scope, subject: subject)
        switch SavedWidgetSelectionStatus10875.of(scope: scope, subject: subject, in: snapshot) {
        case .otherAccount:
            return SavedItemEntity10875(id: id, title: "Saved on another account")
        case .unknown:
            return SavedItemEntity10875(id: id, title: "Open Bain Luck to load your saved items")
        case .removed:
            let held = SavedItemWidgetFetch10875.cache.title(scope: scope, subject: subject)
            return SavedItemEntity10875(id: id, title: "\(held ?? subject.fallbackTitle) (no longer saved)")
        case .saved:
            let title = await SavedItemWidgetFetch10875.payload(for: subject)?.title
                ?? SavedItemWidgetFetch10875.cache.title(scope: scope, subject: subject)
                ?? subject.fallbackTitle
            return SavedItemEntity10875(id: id, title: title)
        }
    }
}

// MARK: - The side or outcome

struct SavedOutcomeEntity10875: AppEntity {
    static var typeDisplayRepresentation: TypeDisplayRepresentation = "Team or outcome"
    static var defaultQuery = SavedOutcomeEntityQuery10875()

    /// "home", "away" or "outcome:<id>".
    let id: String
    let title: String

    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(title)") }

    var side: SavedWidgetGameSide10875? { SavedWidgetGameSide10875(rawValue: id) }
    var outcomeID: Int? {
        guard id.hasPrefix("outcome:") else { return nil }
        return Int(id.dropFirst("outcome:".count))
    }
}

struct SavedOutcomeEntityQuery10875: EntityQuery {
    @IntentParameterDependency<SelectSavedItemIntent10875>(\.$item)
    var configuration

    /// The chosen item's sides (away first, as every card) or its outcomes,
    /// highest-priced first. Empty until an item is chosen.
    func suggestedEntities() async throws -> [SavedOutcomeEntity10875] {
        guard let item = configuration?.item,
              let parsed = SavedWidgetSelection10875.parse(entityID: item.id),
              SavedWidgetSelectionStatus10875.of(scope: parsed.scope, subject: parsed.subject,
                                                 in: SavedItemWidgetFetch10875.bridge) == .saved,
              let payload = await SavedItemWidgetFetch10875.payload(for: parsed.subject)
        else { return [] }
        return Self.options(payload)
    }

    func entities(for identifiers: [SavedOutcomeEntity10875.ID]) async throws -> [SavedOutcomeEntity10875] {
        var options: [SavedOutcomeEntity10875] = []
        if let item = configuration?.item,
           let parsed = SavedWidgetSelection10875.parse(entityID: item.id),
           SavedWidgetSelectionStatus10875.of(scope: parsed.scope, subject: parsed.subject,
                                              in: SavedItemWidgetFetch10875.bridge) == .saved,
           let payload = await SavedItemWidgetFetch10875.payload(for: parsed.subject) {
            options = Self.options(payload)
        }
        return identifiers.map { id in
            options.first { $0.id == id } ?? SavedOutcomeEntity10875(id: id, title: "Chosen outcome")
        }
    }

    static func options(_ payload: SavedWidgetDetailPayload10875) -> [SavedOutcomeEntity10875] {
        switch payload {
        case .game(let event):
            return [SavedOutcomeEntity10875(id: SavedWidgetGameSide10875.away.rawValue, title: event.awayTeam),
                    SavedOutcomeEntity10875(id: SavedWidgetGameSide10875.home.rawValue, title: event.homeTeam)]
        case .market(let market):
            return market.outcomes
                .sorted { ($0.probability ?? -1, -$0.id) > ($1.probability ?? -1, -$1.id) }
                .map { SavedOutcomeEntity10875(id: "outcome:\($0.id)", title: $0.name) }
        }
    }
}

// MARK: - The configuration

struct SelectSavedItemIntent10875: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Choose a saved game or market"
    static var description = IntentDescription(
        "Keep one of your saved games or markets on your Home Screen or Lock Screen.")

    @Parameter(title: "Game or market")
    var item: SavedItemEntity10875?

    @Parameter(title: "Team or outcome",
               description: "Optional. Without one, a game shows the favourite and a market its leading outcome.")
    var outcome: SavedOutcomeEntity10875?

    static var parameterSummary: some ParameterSummary {
        Summary("Show \(\.$item)") {
            \.$outcome
        }
    }

    init() {}

    /// The plain-value selection the timeline reads.
    var selection: SavedWidgetSelection10875? {
        guard let item, let parsed = SavedWidgetSelection10875.parse(entityID: item.id) else { return nil }
        return SavedWidgetSelection10875(
            scope: parsed.scope, subject: parsed.subject,
            side: parsed.subject.kind == .game ? outcome?.side : nil,
            outcomeID: parsed.subject.kind == .market ? outcome?.outcomeID : nil)
    }
}
