#if os(iOS)
import Combine
import Foundation

/// Phone preference authority. WCSession is still owned by WatchTelemetryReceiver.
@MainActor final class WatchMyStuffPublisher {
    nonisolated static let didChangeFavorites = Notification.Name("WatchMyStuff.favoritesChanged")
    private let publisher = UUID() // A restart must be re-established by a paired handshake.
    private var generation = 0
    private var revision = 0
    private var binding: PinAccountBinding?
    private weak var pins: PinManager?
    private var subscription: AnyCancellable?
    private var observer: NSObjectProtocol?
    private var pinTask: Task<Void, Never>?
    private var pinReloadTask: Task<Void, Never>?
    private var pinReloadToken = UUID()
    private var teamTask: Task<Void, Never>?
    private var pinToken = UUID()
    private var pinSignature: [SavedPin]?
    private var pinSection = WatchMyStuffSnapshot.Section()
    private var teamSection = WatchMyStuffSnapshot.Section()
    private var validUntil = Date.distantPast
    private(set) var snapshot: WatchMyStuffSnapshot?
    var publish: (Data) -> Void = { _ in }

    private let fetchPreferences: () async throws -> PreferencesResponse
    private let lookupPin: (SavedPin) async -> PinMetadata

    init(fetchPreferences: @escaping () async throws -> PreferencesResponse = { try await APIClient.shared.fetchPreferences() },
         lookupPin: @escaping (SavedPin) async -> PinMetadata = PinManagementViewModel.lookupPin) {
        self.fetchPreferences = fetchPreferences
        self.lookupPin = lookupPin
        observer = NotificationCenter.default.addObserver(
            forName: Self.didChangeFavorites, object: nil, queue: .main
        ) { [weak self] _ in Task { @MainActor in self?.refreshTeams() } }
    }

    func bind(_ identity: PinAccountBinding, pins: PinManager) {
        if self.pins !== pins {
            self.pins = pins
            subscription = pins.objectWillChange.sink { [weak self] _ in
                // @Published emits before mutation. Read the completed transaction.
                Task { @MainActor in
                    await Task.yield()
                    self?.refreshPins()
                }
            }
        }
        guard binding != identity else { return }
        binding = identity
        generation += 1
        pinTask?.cancel(); teamTask?.cancel(); teamTask = nil
        pinReloadTask?.cancel(); pinReloadTask = nil; pinReloadToken = UUID()
        pinToken = UUID(); pinSignature = nil
        pinSection = .init(); teamSection = .init()
        validUntil = Date().addingTimeInterval(WatchMyStuffSnapshot.maxSessionAge)
        // Publish the empty account transition before any new personal content.
        emit(account: identity.userID == nil ? .signedOut : .connecting)
        guard identity.authenticated, identity.userID != nil else { return }
        refreshPins()
        refreshTeams()
    }

    func refresh() {
        guard binding?.authenticated == true else { return }
        refreshPins(retryMetadata: true)
        refreshTeams()
        if let pins, pinReloadTask == nil, pins.loadState != .loading, pins.savingKeys.isEmpty {
            let token = UUID(); pinReloadToken = token
            pinReloadTask = Task { [weak self] in
                await pins.loadPins()
                guard let self, self.pinReloadToken == token else { return }
                self.pinReloadTask = nil
                self.refreshPins()
            }
        }
    }

    func refreshPins(retryMetadata: Bool = false) {
        guard binding?.authenticated == true, let pins else { return }
        if !pins.savingKeys.isEmpty {
            // Never promote optimistic adds/removals as confirmed phone state.
            pinToken = UUID(); pinTask?.cancel(); pinSignature = nil
            pinSection.state = .pending
            emit(); return
        }
        let state: WatchMyStuffSnapshot.State = (pins.loadState == .failed || pins.watchPinSaveFailed) ? .failed
            : (pins.loadState == .loaded ? .loaded : .loading)
        guard let all = pins.confirmedPinsForWatch else {
            pinSection.state = state
            emit(); return
        }
        if pinSignature == all, !retryMetadata {
            pinSection.state = state
            pinSection.syncedAt = pins.confirmedPinsForWatchAt
            emit(); return
        }
        pinSignature = all
        pinTask?.cancel()
        let token = UUID(); pinToken = token
        let epoch = generation
        let selected = Array(all.prefix(WatchMyStuffSnapshot.maxItems))
        let oldTitles = Dictionary(uniqueKeysWithValues: pinSection.items.map { ($0.id, $0) })
        pinSection = .init(state: state, items: selected.map { pin in
            let key = "\(pin.type):\(pin.value):"
            return oldTitles[key] ?? .init(kind: pin.type, targetID: pin.value, relation: nil,
                                          title: "\(pin.fallbackTitle) #\(pin.value)")
        }, syncedAt: pins.confirmedPinsForWatchAt, omittedCount: max(0, all.count - selected.count))
        emit() // A confirmed unpin removes the row before slow metadata completes.
        pinTask = Task { [weak self] in
            for pin in selected {
                guard !Task.isCancelled else { return }
                guard pin.type == "event" || pin.type == "future" else { continue }
                guard let self else { return }
                let metadata = await self.lookupPin(pin)
                guard !Task.isCancelled, self.generation == epoch,
                      self.pinToken == token else { return }
                if let index = self.pinSection.items.firstIndex(where: {
                    $0.kind == pin.type && $0.targetID == pin.value
                }) {
                    switch metadata {
                    case .available(let title):
                        self.pinSection.items[index].title = Self.boundedTitle(title)
                        self.pinSection.items[index].unavailable = false
                    case .unavailable: self.pinSection.items[index].unavailable = true
                    case .failed: break // Keep the identity and last good title; opening can retry.
                    }
                    self.emit()
                }
            }
        }
    }

    func refreshTeams() {
        guard binding?.authenticated == true else { return }
        teamTask?.cancel()
        let epoch = generation
        let request = UUID()
        teamRequest = request
        teamSection.state = .loading
        emit()
        teamTask = Task { [weak self] in
            do {
                guard let self else { return }
                let prefs = try await self.fetchPreferences()
                guard !Task.isCancelled, self.generation == epoch,
                      self.teamRequest == request else { return }
                var seen = Set<String>()
                let items = prefs.favorites.map {
                    WatchMyStuffSnapshot.Item(kind: "team", targetID: $0.teamId,
                        relation: $0.relationType, title: Self.boundedTitle($0.teamName))
                }.filter { $0.targetID > 0 && seen.insert($0.id).inserted }
                self.teamSection = .init(state: .loaded,
                    items: Array(items.prefix(WatchMyStuffSnapshot.maxItems)), syncedAt: Date(),
                    omittedCount: max(0, items.count - WatchMyStuffSnapshot.maxItems))
                self.validUntil = Date().addingTimeInterval(WatchMyStuffSnapshot.maxSessionAge)
                self.emit()
            } catch {
                guard let self, !Task.isCancelled, self.generation == epoch,
                      self.teamRequest == request else { return }
                self.teamSection.state = .failed // Preserve same-generation last-good rows.
                self.emit()
            }
        }
    }
    private var teamRequest = UUID()

    static func boundedTitle(_ text: String) -> String {
        // A visible ellipsis indicates shortened labels; exact detail retains full text.
        text.count > 400 ? String(text.prefix(400)) + "…" : text
    }

    private func emit(account: WatchMyStuffSnapshot.Account? = nil) {
        revision += 1
        let state = account ?? (binding?.authenticated == true ? .signedIn :
            (binding?.userID == nil ? .signedOut : .connecting))
        var value = WatchMyStuffSnapshot(version: 1, publisher: publisher, generation: generation,
            revision: revision, sampledAt: Date(), validUntil: validUntil, account: state,
            pins: state == .signedIn ? pinSection : .init(),
            teams: state == .signedIn ? teamSection : .init())
        // Keep a decodable packet under WCSession's application-context limit.
        while let data = try? JSONEncoder().encode(value), data.count > WatchMyStuffSnapshot.maxBytes {
            if !value.teams.items.isEmpty {
                value.teams.items.removeLast(); value.teams.omittedCount += 1
            } else if !value.pins.items.isEmpty {
                value.pins.items.removeLast(); value.pins.omittedCount += 1
            } else { return }
        }
        guard let data = try? JSONEncoder().encode(value) else { return }
        snapshot = value
        publish(data)
    }
}
#endif
