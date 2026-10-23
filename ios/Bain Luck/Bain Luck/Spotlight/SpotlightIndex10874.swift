import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "spotlight")

/// #10874 — the writes Spotlight needs, behind a seam so ordering and
/// account fencing are unit tests. Production is `SpotlightSystemIndexClient10874`.
protocol SpotlightIndexClient10874: AnyObject {
    func index(_ items: [SpotlightIndexItem10874]) async throws
    func delete(identifiers: [String]) async throws
    /// Deletes every item in `domain` and in every domain beneath it.
    func deleteDomain(_ domain: String) async throws
}

/// #10874 — this device's saved/recent descriptions, one account at a time,
/// in UserDefaults under the same kind of namespace `PinManager` uses.
struct SpotlightStore10874 {
    static let keyPrefix = "bainluck_spotlight10874."
    static let lastScopeKey = "bainluck_spotlight10874_last_scope"

    let defaults: UserDefaults

    func load(scope: String) -> [SpotlightEntry10874] {
        guard let data = defaults.data(forKey: Self.keyPrefix + scope),
              let entries = try? JSONDecoder().decode([SpotlightEntry10874].self, from: data) else { return [] }
        return entries
    }

    func save(_ entries: [SpotlightEntry10874], scope: String) {
        guard let data = try? JSONEncoder().encode(entries) else { return }
        defaults.set(data, forKey: Self.keyPrefix + scope)
    }

    func remove(scope: String) { defaults.removeObject(forKey: Self.keyPrefix + scope) }

    var lastScope: String? {
        get { defaults.string(forKey: Self.lastScopeKey) }
        nonmutating set { defaults.set(newValue, forKey: Self.lastScopeKey) }
    }
}

/// #10874 — keeps Spotlight equal to `SpotlightIndexPlan10874.items` for the
/// account the app is signed in to.
///
/// Account contract:
/// * Only one account's entries exist, in the store or in Spotlight. Binding a
///   different account deletes the previous account's stored descriptions and
///   purges the whole root domain before anything of the new account is
///   written.
/// * Every write runs on one serial chain, each after the previous one has
///   completed. A write that was already in flight when the account changed
///   therefore lands BEFORE the purge queued behind it, so it cannot outlive
///   the switch. A pass reads the account, entries and pins when it RUNS, not
///   when it was queued, so a pass queued under the old account writes only
///   the new account's state, after its purge.
/// * A purge still in flight when the account changes does not count as the
///   new account's purge (`generation`): the new account purges again.
/// * Saved pins and My Stuff's descriptions are accepted only while they come
///   from a `PinManager` bound to this same account (`pinUserID`), so a pin
///   set or a late lookup from the previous account is refused, not indexed.
///
/// Nothing here promises Spotlight shows an entry at once or ranks it: the
/// system indexes and ranks on its own schedule.
final class SpotlightIndex10874 {
    static var isEnabledOnThisPlatform: Bool {
        #if os(iOS)
        true
        #else
        false
        #endif
    }

    static let shared = SpotlightIndex10874(
        client: isEnabledOnThisPlatform ? SpotlightSystemIndexClient10874.makeIfAvailable() : nil,
        store: SpotlightStore10874(defaults: .standard))

    /// The first sync of a launch waits this long, so building and writing the
    /// index never competes with the first screen's own loads.
    static let launchDelay: TimeInterval = 5

    private let client: SpotlightIndexClient10874?
    private let store: SpotlightStore10874
    private let now: () -> Date
    private(set) var scope: String?
    private(set) var entries: [SpotlightEntry10874] = []
    private(set) var saved: Set<StoryContinuationDestination> = []
    /// Whether this account's pins have arrived since `bind`. Until they have,
    /// a saved-only description is kept on disk rather than pruned as unsaved.
    private var savedKnown = false
    private(set) var applied: [String: SpotlightIndexItem10874] = [:]
    private var generation = 0
    private var needsPurge = false
    private var tail: Task<Void, Never>?

    init(client: SpotlightIndexClient10874?, store: SpotlightStore10874, now: @escaping () -> Date = Date.init) {
        self.client = client
        self.store = store
        self.now = now
    }

    // MARK: - Inputs

    /// The signed-in account (or none). A change purges before rebuilding.
    @discardableResult
    func bind(userID: String?, delay: TimeInterval = 0) -> Task<Void, Never>? {
        let next = SpotlightIndexPlan10874.scope(userID: userID)
        guard next != scope else { return tail }
        generation += 1
        if let previous = scope ?? store.lastScope, previous != next {
            store.remove(scope: previous)
        }
        store.lastScope = next
        scope = next
        entries = store.load(scope: next)
        saved = []
        savedKnown = false
        needsPurge = true
        return enqueueSync(delay: delay)
    }

    /// The pins of the account `pinUserID` is bound to. Ignored unless that is
    /// this index's account.
    @discardableResult
    func savedChanged(_ pins: [SavedPin], pinUserID: String?) -> Task<Void, Never>? {
        guard accepts(pinUserID) else { return nil }
        let next = Set(pins.compactMap(Self.destination))
        guard next != saved || !savedKnown else { return nil }
        saved = next
        savedKnown = true
        return enqueueSync()
    }

    /// A detail page the reader actually viewed: on screen, in the foreground,
    /// loaded, for `viewDwell`.
    @discardableResult
    func recordViewed(_ subject: SpotlightSubject10874) -> Task<Void, Never>? {
        guard scope != nil else { return nil }
        entries.removeAll { $0.subject.destination == subject.destination }
        entries.append(SpotlightEntry10874(subject: subject, viewedAt: now()))
        return persistAndSync()
    }

    /// My Stuff described saved pins from their detail payloads, or the server
    /// said one is gone (404/410). Only pins this account has saved count —
    /// none before its pins arrive — so a late lookup cannot add a subject.
    @discardableResult
    func learnSaved(_ answers: [StoryContinuationDestination: SpotlightSavedAnswer10874],
                    pinUserID: String?) -> Task<Void, Never>? {
        guard accepts(pinUserID) else { return nil }
        var changed = false
        for (destination, answer) in answers where saved.contains(destination) {
            switch answer {
            case .described(let subject):
                changed = learn(subject) || changed
            case .gone:
                let before = entries.count
                entries.removeAll { $0.subject.destination == destination }
                changed = changed || entries.count != before
            }
        }
        return changed ? persistAndSync() : nil
    }

    /// Time alone can expire an entry; called when the app comes forward.
    @discardableResult
    func refresh() -> Task<Void, Never>? {
        guard scope != nil else { return nil }
        return enqueueSync()
    }

    // MARK: - Internals

    static func destination(_ pin: SavedPin) -> StoryContinuationDestination? {
        guard pin.value > 0 else { return nil }
        switch pin.type {
        case "event": return .event(pin.value)
        case "future": return .futures(pin.value)
        default: return nil
        }
    }

    private func accepts(_ pinUserID: String?) -> Bool {
        scope != nil && SpotlightIndexPlan10874.scope(userID: pinUserID) == scope
    }

    /// Adds or updates a saved-only description; `true` when it changed. A
    /// subject the reader viewed keeps its page's own description: the page
    /// may ask for a different title representation than My Stuff does, and
    /// the two must not take turns rewriting the entry.
    private func learn(_ subject: SpotlightSubject10874) -> Bool {
        if let index = entries.firstIndex(where: { $0.subject.destination == subject.destination }) {
            guard entries[index].viewedAt == nil, entries[index].subject != subject else { return false }
            entries[index].subject = subject
        } else {
            entries.append(SpotlightEntry10874(subject: subject, viewedAt: nil))
        }
        return true
    }

    private func persistAndSync() -> Task<Void, Never>? {
        guard let scope else { return nil }
        let keepSavedOnly = savedKnown ? [] : entries.filter { $0.viewedAt == nil }.map(\.subject.destination)
        entries = SpotlightIndexPlan10874.prune(entries, saved: saved.union(keepSavedOnly), now: now())
        store.save(entries, scope: scope)
        return enqueueSync()
    }

    private func enqueueSync(delay: TimeInterval = 0) -> Task<Void, Never>? {
        guard client != nil else { return nil }
        let previous = tail
        let generation = generation
        let task = Task { @MainActor [weak self] in
            await previous?.value
            if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
            await self?.sync(generation: generation)
        }
        tail = task
        return task
    }

    /// One pass: purge if owed, then the diff from what was last written.
    /// Any failure turns the next pass into a full purge-and-rebuild, because
    /// `applied` can no longer be trusted to describe the system index.
    private func sync(generation: Int) async {
        guard let client else { return }
        if needsPurge {
            do {
                try await client.deleteDomain(SpotlightIndexPlan10874.rootDomain)
            } catch {
                logger.error("Spotlight purge failed: \(error.localizedDescription, privacy: .public)")
                return
            }
            guard generation == self.generation else { return }
            needsPurge = false
            applied = [:]
        }
        guard let scope else { return }
        let desired = SpotlightIndexPlan10874.items(entries, saved: saved, scope: scope, now: now())
        let (upserts, deletes) = SpotlightIndexPlan10874.diff(applied: applied, desired: desired)
        do {
            if !upserts.isEmpty {
                try await client.index(upserts)
                for item in upserts { applied[item.identifier] = item }
            }
            if !deletes.isEmpty {
                try await client.delete(identifiers: deletes)
                for identifier in deletes { applied[identifier] = nil }
            }
        } catch {
            logger.error("Spotlight write failed: \(error.localizedDescription, privacy: .public)")
            needsPurge = true
        }
    }
}
