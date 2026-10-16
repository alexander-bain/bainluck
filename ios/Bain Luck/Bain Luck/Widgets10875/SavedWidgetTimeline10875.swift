import Foundation

/// #10875 — one widget instance's configuration, as plain values: the item it
/// follows, the account scope it was chosen under, and the side or outcome it
/// names. Two instances are two of these; nothing here is shared between them.
nonisolated struct SavedWidgetSelection10875: Equatable, Sendable {
    let scope: String
    let subject: SavedWidgetSubject10875
    /// A game's chosen side; nil follows the favourite, as the hero leads.
    let side: SavedWidgetGameSide10875?
    /// A market's chosen outcome; nil follows the market page's hero leg.
    let outcomeID: Int?

    /// The entity id the configuration stores: "<scope>|game:123".
    var entityID: String { Self.entityID(scope: scope, subject: subject) }

    static func entityID(scope: String, subject: SavedWidgetSubject10875) -> String {
        "\(scope)|\(subject.token)"
    }

    static func parse(entityID: String) -> (scope: String, subject: SavedWidgetSubject10875)? {
        guard let bar = entityID.lastIndex(of: "|") else { return nil }
        let scope = String(entityID[..<bar])
        guard !scope.isEmpty, let subject = SavedWidgetSubject10875(token: String(entityID[entityID.index(after: bar)...]))
        else { return nil }
        return (scope, subject)
    }
}

/// A fetched detail, kept as decoded values so each timeline entry can be read
/// at its own date.
nonisolated enum SavedWidgetDetailPayload10875: Equatable, Sendable {
    case game(SavedWidgetEventDetail10875)
    case market(SavedWidgetMarketDetail10875)

    static func decode(_ data: Data, as kind: SavedWidgetSubject10875.Kind) throws -> Self {
        let decoder = SavedWidgetDetailDecoding10875.decoder()
        switch kind {
        case .game: return .game(try decoder.decode(SavedWidgetEventDetail10875.self, from: data))
        case .market: return .market(try decoder.decode(SavedWidgetMarketDetail10875.self, from: data))
        }
    }

    var id: Int {
        switch self {
        case .game(let event): return event.id
        case .market(let market): return market.id
        }
    }

    var title: String {
        switch self {
        case .game(let event): return "\(event.awayTeam) vs \(event.homeTeam)"
        case .market(let market): return market.name
        }
    }
}

/// What one widget instance shows, before a date is applied.
nonisolated enum SavedWidgetContent10875: Equatable, Sendable {
    /// The live reading. `offline` when the network failed and this is the
    /// last detail this account's widget received, read again at the entry's
    /// own date — so a price that was current goes on ageing into "last
    /// recorded", and a final result stays final.
    case detail(SavedWidgetDetailPayload10875, offline: Bool)
    /// Nothing chosen yet.
    case notConfigured
    /// The app has not told the widget whose saved items these are.
    case openApp
    /// Chosen under another account, or signed out since. Nothing about the
    /// item is shown.
    case otherAccount
    /// The reader's own item, no longer saved. The title is shown only when
    /// this account's widget already holds it; it is never fetched for this.
    case removed(title: String?)
    /// The detail answered "not found".
    case gone
    /// No network and nothing held for this account.
    case unreachable
}

nonisolated enum SavedWidgetFetchError10875: Error, Equatable {
    case notFound
    case failed
}

/// The last detail each item's widget received, held in the widget
/// extension's OWN defaults (not the shared group), keyed by account scope.
/// Writing for one scope clears every other scope's, so a previous account's
/// details do not outlive the switch on disk.
nonisolated struct SavedWidgetDetailCache10875 {
    let defaults: UserDefaults
    static let key = "bainluck.widget.detailCache.v1"

    private func load() -> [String: Data] {
        (defaults.dictionary(forKey: Self.key) as? [String: Data]) ?? [:]
    }

    func data(scope: String, subject: SavedWidgetSubject10875) -> Data? {
        load()[SavedWidgetSelection10875.entityID(scope: scope, subject: subject)]
    }

    func store(_ data: Data, scope: String, subject: SavedWidgetSubject10875) {
        var held = load().filter { $0.key.hasPrefix(scope + "|") }
        held[SavedWidgetSelection10875.entityID(scope: scope, subject: subject)] = data
        defaults.set(held, forKey: Self.key)
    }

    /// Drops everything not belonging to `scope`.
    func keepOnly(scope: String?) {
        let held = load()
        let kept = scope.map { s in held.filter { $0.key.hasPrefix(s + "|") } } ?? [:]
        if kept.count != held.count { defaults.set(kept, forKey: Self.key) }
    }

    func title(scope: String, subject: SavedWidgetSubject10875) -> String? {
        data(scope: scope, subject: subject)
            .flatMap { try? SavedWidgetDetailPayload10875.decode($0, as: subject.kind) }?.title
    }
}

enum SavedWidgetTimeline10875 {
    /// Decides what one instance shows. `readBridge` is read twice: before the
    /// fetch, and again after it returns, because the reader can sign out or
    /// unpin while the request is in flight. A detail fetched for an item that
    /// is no longer the current account's saved item is discarded, not shown
    /// and not cached.
    static func resolve(
        _ selection: SavedWidgetSelection10875?,
        readBridge: () -> SavedWidgetSnapshot10875?,
        fetch: (SavedWidgetSubject10875) async throws -> Data,
        cache: SavedWidgetDetailCache10875
    ) async -> SavedWidgetContent10875 {
        guard let selection else { return .notConfigured }
        if let early = unavailable(selection, readBridge(), cache: cache) { return early }

        let fetched: Result<Data, SavedWidgetFetchError10875>
        do {
            fetched = .success(try await fetch(selection.subject))
        } catch let error as SavedWidgetFetchError10875 {
            fetched = .failure(error)
        } catch {
            fetched = .failure(.failed)
        }

        // The second read: the answer belongs to the account that is current
        // NOW, or to nobody.
        if let late = unavailable(selection, readBridge(), cache: cache) { return late }

        switch fetched {
        case .success(let data):
            guard let payload = try? SavedWidgetDetailPayload10875.decode(data, as: selection.subject.kind),
                  answers(selection.subject, with: payload)
            else { return held(selection, cache: cache) }
            cache.store(data, scope: selection.scope, subject: selection.subject)
            return .detail(payload, offline: false)
        case .failure(.notFound):
            return .gone
        case .failure(.failed):
            return held(selection, cache: cache)
        }
    }

    /// Whether a fetched detail is the one the page this widget opens draws.
    /// A saved game that is a proven duplicate is served AS its canonical row
    /// (another id), and the event page adopts it with no id check, so the
    /// widget does too — held under the id the reader saved. The market page
    /// refuses an answer for another id (`fetched.id == marketId`), so a market
    /// widget refuses it too.
    private static func answers(_ subject: SavedWidgetSubject10875,
                                with payload: SavedWidgetDetailPayload10875) -> Bool {
        switch subject.kind {
        case .game: return true
        case .market: return payload.id == subject.id
        }
    }

    /// The states decided by the saved set alone, or nil when the item is the
    /// current reader's saved item.
    private static func unavailable(_ selection: SavedWidgetSelection10875,
                                    _ snapshot: SavedWidgetSnapshot10875?,
                                    cache: SavedWidgetDetailCache10875) -> SavedWidgetContent10875? {
        switch SavedWidgetSelectionStatus10875.of(scope: selection.scope, subject: selection.subject, in: snapshot) {
        case .saved:
            return nil
        case .unknown:
            return .openApp
        case .otherAccount:
            cache.keepOnly(scope: snapshot?.scope)
            return .otherAccount
        case .removed:
            return .removed(title: cache.title(scope: selection.scope, subject: selection.subject))
        }
    }

    private static func held(_ selection: SavedWidgetSelection10875,
                             cache: SavedWidgetDetailCache10875) -> SavedWidgetContent10875 {
        guard let data = cache.data(scope: selection.scope, subject: selection.subject),
              let payload = try? SavedWidgetDetailPayload10875.decode(data, as: selection.subject.kind)
        else { return .unreachable }
        return .detail(payload, offline: true)
    }

    /// The reading at `date`.
    static func reading(_ payload: SavedWidgetDetailPayload10875, selection: SavedWidgetSelection10875,
                        at date: Date) -> SavedWidgetReading10875 {
        switch payload {
        case .game(let event): return SavedWidgetReadingRules10875.game(event, side: selection.side, now: date)
        case .market(let market): return SavedWidgetReadingRules10875.market(market, outcomeID: selection.outcomeID, now: date)
        }
    }

    /// The dates a timeline needs: now, and the instant a current price stops
    /// being current on its own clock (a second entry WidgetKit shows without
    /// a new fetch).
    static func entryDates(_ content: SavedWidgetContent10875, selection: SavedWidgetSelection10875?,
                           now: Date) -> [Date] {
        guard case .detail(let payload, _) = content, let selection,
              let flip = reading(payload, selection: selection, at: now).becomesLastRecordedAt,
              flip > now else { return [now] }
        // One second past the bound: the rule is strictly "older than".
        return [now, flip.addingTimeInterval(1)]
    }

    /// When to ASK WidgetKit for another timeline. A request, not a promise:
    /// the system's budget decides when, so every entry carries its own clock.
    static func nextRequest(_ content: SavedWidgetContent10875, selection: SavedWidgetSelection10875?,
                            now: Date) -> Date {
        let minutes: Double
        switch content {
        case .detail(let payload, let offline):
            if offline {
                minutes = 15
            } else if let selection {
                switch reading(payload, selection: selection, at: now).phase {
                case .result, .noResult: minutes = 6 * 60
                case .current, .lastRecorded, .openingLine, .unavailable:
                    if case .game(let event) = payload, event.status == "live" { minutes = 15 } else { minutes = 30 }
                }
            } else {
                minutes = 30
            }
        case .unreachable:
            minutes = 15
        case .notConfigured, .openApp, .otherAccount, .removed, .gone:
            // The app asks for a reload whenever the saved set or the account
            // changes; this is only the backstop.
            minutes = 60
        }
        return now.addingTimeInterval(minutes * 60)
    }
}

/// What a widget says when it has no reading to show.
nonisolated struct SavedWidgetMessage10875: Equatable, Sendable {
    let title: String
    let detail: String

    var spoken: String { "\(title). \(detail)" }

    init(_ content: SavedWidgetContent10875) {
        switch content {
        case .notConfigured:
            title = "Choose a saved game or market"
            detail = "Touch and hold, then Edit Widget."
        case .openApp:
            title = "Open Bain Luck"
            detail = "Your saved games and markets will appear here."
        case .otherAccount:
            title = "Saved on another account"
            detail = "Edit the widget to choose from your saved items."
        case .removed(let name):
            title = name ?? "No longer saved"
            detail = name == nil ? "Edit the widget to choose another." : "No longer saved. Edit the widget to choose another."
        case .gone:
            title = "No longer listed"
            detail = "Edit the widget to choose another."
        case .unreachable:
            title = "Can't reach Bain Luck"
            detail = "This will update when you're back online."
        case .detail:
            title = ""
            detail = ""
        }
    }
}
