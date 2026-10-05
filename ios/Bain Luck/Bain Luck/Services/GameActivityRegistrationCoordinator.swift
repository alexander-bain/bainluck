#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import Foundation

/// Registration is optional: foreground activities remain available anonymously.
/// A stopped identity is never registered again, even if an in-flight PUT succeeds.
@MainActor final class GameActivityRegistrationCoordinator {
    static let shared = GameActivityRegistrationCoordinator()
    private struct Session {
        let owner: Int
        let bearer: String
    }
    private final class Entry {
        let eventID: Int
        var session: Session
        var token: String?
        var stopped = false
        var version = 0
        var needsRetry = false
        var pendingMutation: (token: String?, version: Int, id: UUID)?
        var worker: Task<Void, Never>?
        var observation: Task<Void, Never>?
        var stateObservation: Task<Void, Never>?
        init(eventID: Int, session: Session) { self.eventID = eventID; self.session = session }
    }
    private let transport: any GameActivityRegistrationTransport
    private let defaults: UserDefaults
    private var session: Session?
    private var entries: [String: Entry] = [:]
    private let ownershipKey = "gameActivityRegistrationOwners"
    private let stoppedKey = "gameActivityRegistrationStoppedIDs"
    private var stoppedIDs: Set<String> = []
    private(set) var unconfirmedRevocations: Set<String> = []
    var canRequestPushToken: Bool { session != nil }

    convenience init() { self.init(transport: GameActivityRegistrationClient()) }

    init(transport: any GameActivityRegistrationTransport, defaults: UserDefaults = .standard) {
        self.transport = transport
        self.defaults = defaults
        stoppedIDs = Set(defaults.stringArray(forKey: stoppedKey) ?? [])
        unconfirmedRevocations = stoppedIDs
    }

    /// Called only after backend authentication succeeds, never on optimistic restore.
    func setSession(owner: Int?, bearer: String?) {
        if (session != nil && session?.owner != owner) || owner == nil { invalidateSession() }
        guard let owner, let bearer, !bearer.isEmpty else { session = nil; return }
        session = Session(owner: owner, bearer: bearer)
        for entry in entries.values where !entry.stopped && entry.session.owner == owner {
            entry.session = Session(owner: owner, bearer: bearer)
        }
        foregroundActivated()
        // Only a persisted same-account binding may be restored. Anonymous activities
        // are never upgraded and another account's activity is never adopted.
        for activity in Activity<GameActivityAttributes>.activities {
            let owners = defaults.dictionary(forKey: ownershipKey) ?? [:]
            guard (owners[activity.id] as? Int) == owner else { continue }
            if stoppedIDs.contains(activity.id) {
                // A relaunch must spend persisted stop intent on DELETE only.
                if entries[activity.id] == nil {
                    let entry = Entry(eventID: activity.attributes.eventID, session: session!)
                    entry.stopped = true
                    entries[activity.id] = entry
                    startWorker(id: activity.id, entry: entry)
                }
                Task { await activity.end(nil, dismissalPolicy: .immediate) }
            } else { observe(activity) }
        }
    }

    /// Real activation/auth refresh permits one bounded recovery attempt. No timer,
    /// anonymous adoption or stopped identity can restart a registration.
    func foregroundActivated() {
        guard let session else { return }
        for (id, entry) in entries where !entry.stopped && entry.needsRetry
            && entry.session.owner == session.owner {
            startWorker(id: id, entry: entry)
        }
    }

    /// Synchronous latch runs before Keychain deletion. Local dismissal never waits
    /// for network revocation; the captured old credential lives only in bounded work.
    func invalidateSession() {
        session = nil
        let owned = defaults.dictionary(forKey: ownershipKey) ?? [:]
        stoppedIDs.formUnion(owned.keys)
        persistStoppedIDs()
        unconfirmedRevocations.formUnion(owned.keys)
        for id in Array(entries.keys) { stop(id: id) }
        for activity in Activity<GameActivityAttributes>.activities where owned[activity.id] != nil {
            Task { await activity.end(nil, dismissalPolicy: .immediate) }
        }
    }

    func observe(_ activity: Activity<GameActivityAttributes>) {
        guard let session, entries[activity.id] == nil, !stoppedIDs.contains(activity.id) else { return }
        bind(id: activity.id, eventID: activity.attributes.eventID)
        var owners = defaults.dictionary(forKey: ownershipKey) ?? [:]
        owners[activity.id] = session.owner
        defaults.set(owners, forKey: ownershipKey)
        if let token = activity.pushToken { receive(id: activity.id, token: token) }
        entries[activity.id]?.observation = Task { [weak self] in
            for await token in activity.pushTokenUpdates {
                guard !Task.isCancelled else { break }
                self?.receive(id: activity.id, token: token)
            }
        }
        entries[activity.id]?.stateObservation = Task { [weak self] in
            for await state in activity.activityStateUpdates {
                guard !Task.isCancelled else { break }
                if state == .ended || state == .dismissed {
                    self?.stop(id: activity.id)
                    break
                }
            }
        }
    }

    // Separate from ActivityKit for deterministic lifecycle tests.
    func bind(id: String, eventID: Int) {
        guard let session, entries[id] == nil, !stoppedIDs.contains(id) else { return }
        entries[id] = Entry(eventID: eventID, session: session)
    }
    func receive(id: String, token: Data) {
        guard let entry = entries[id], !entry.stopped, session?.owner == entry.session.owner else { return }
        entry.token = token.map { String(format: "%02x", $0) }.joined()
        startWorker(id: id, entry: entry)
    }
    func stop(id: String) {
        guard let entry = entries[id] else { return }
        entry.stopped = true
        // Write the latch before launching either network or local ending work.
        stoppedIDs.insert(id)
        persistStoppedIDs()
        entry.observation?.cancel()
        entry.observation = nil
        entry.stateObservation?.cancel()
        entry.stateObservation = nil
        unconfirmedRevocations.insert(id)
        startWorker(id: id, entry: entry)
    }
    private func startWorker(id: String, entry: Entry) {
        guard entry.worker == nil else { return }
        entry.worker = Task { [weak self] in
            guard let self else { return }
            await self.drain(id: id, entry: entry)
            entry.worker = nil
            if entry.stopped {
                // Discard captured credentials regardless of the remote result.
                self.entries.removeValue(forKey: id)
            }
        }
    }
    private func persistStoppedIDs() {
        defaults.set(Array(stoppedIDs).sorted(), forKey: stoppedKey)
        // Unlike ordinary preferences, this is a crash-recovery latch. Flush it
        // before allowing asynchronous network or ActivityKit work to begin.
        _ = defaults.synchronize()
    }
    private func acknowledgeRevocation(id: String) {
        unconfirmedRevocations.remove(id)
        stoppedIDs.remove(id)
        persistStoppedIDs()
        var owners = defaults.dictionary(forKey: ownershipKey) ?? [:]
        owners.removeValue(forKey: id)
        defaults.set(owners, forKey: ownershipKey)
    }
    private func drain(id: String, entry: Entry) async {
        var conflicts = 0
        while conflicts < 3 {
            let stopping = entry.stopped
            guard stopping || entry.token != nil else { return }
            let token = stopping ? nil : entry.token
            let bearer = entry.session.bearer
            if entry.pendingMutation?.token != token || entry.pendingMutation?.version != entry.version {
                entry.pendingMutation = (token, entry.version, UUID())
            }
            let mutationID = entry.pendingMutation!.id
            entry.needsRetry = false
            do {
                let metadata = try await transport.mutate(id: id, eventID: entry.eventID,
                    token: token, version: entry.version, mutationID: mutationID, bearer: bearer)
                guard metadata.eventID == entry.eventID else { return }
                entry.version = metadata.version
                entry.pendingMutation = nil
                if stopping {
                    guard !metadata.isActive else { return }
                    acknowledgeRevocation(id: id)
                    return
                }
                // Stop or rotation during the suspended request wins immediately.
                if entry.stopped || entry.token != token { continue }
                return
            } catch GameActivityRegistrationError.conflict {
                conflicts += 1
                entry.pendingMutation = nil
                do {
                    let metadata = try await transport.read(id: id, bearer: entry.session.bearer)
                    guard metadata.eventID == entry.eventID else { return }
                    entry.version = metadata.version
                    if !metadata.isActive {
                        if entry.stopped { acknowledgeRevocation(id: id) }
                        return
                    }
                } catch { entry.needsRetry = !entry.stopped; return }
            } catch {
                // A failed in-flight registration still owes a DELETE tombstone
                // when stop arrived while awaiting it. Ordinary failures stay quiet.
                if !stopping && (entry.stopped || entry.token != token) { continue }
                entry.needsRetry = !entry.stopped
                return
            }
        }
        entry.needsRetry = !entry.stopped
    }
}
#endif
