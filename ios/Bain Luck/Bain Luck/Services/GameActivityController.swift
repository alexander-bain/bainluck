#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import Combine
import Foundation
import UIKit

struct GameActivityRecord {
    let id: String
    let eventID: Int
    let snapshot: GameActivitySnapshot
}

/// Injected boundary keeps orchestration tests independent of ActivityKit/device state.
@MainActor protocol GameActivityServing {
    var isEnabled: Bool { get }
    var records: [GameActivityRecord] { get }
    func request(_ snapshot: GameActivitySnapshot, staleDate: Date) throws
    func update(id: String, snapshot: GameActivitySnapshot, staleDate: Date) async
    func end(id: String, final: GameActivitySnapshot?) async
}

@MainActor private final class SystemGameActivityService: GameActivityServing {
    var isEnabled: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }
    private var activities: [Activity<GameActivityAttributes>] {
        Activity<GameActivityAttributes>.activities.filter {
            $0.activityState == .active || $0.activityState == .stale
        }
    }
    var records: [GameActivityRecord] {
        activities.map { GameActivityRecord(id: $0.id, eventID: $0.attributes.eventID,
                                            snapshot: $0.content.state.snapshot) }
    }
    func request(_ snapshot: GameActivitySnapshot, staleDate: Date) throws {
        _ = try Activity<GameActivityAttributes>.request(
            attributes: GameActivityAttributes(eventID: snapshot.eventID),
            content: ActivityContent(state: .init(snapshot: snapshot), staleDate: staleDate),
            pushType: nil
        )
    }
    func update(id: String, snapshot: GameActivitySnapshot, staleDate: Date) async {
        guard let activity = activities.first(where: { $0.id == id }) else { return }
        await activity.update(ActivityContent(state: .init(snapshot: snapshot), staleDate: staleDate))
    }
    func end(id: String, final: GameActivitySnapshot?) async {
        guard let activity = activities.first(where: { $0.id == id }) else { return }
        let content = final.map { ActivityContent(state: GameActivityAttributes.ContentState(snapshot: $0), staleDate: nil) }
        await activity.end(content, dismissalPolicy: final == nil ? .immediate : .default)
    }
}

/// One explicit game, with foreground-only delivery. No push token is requested.
@MainActor final class GameActivityController: ObservableObject {
    static let shared = GameActivityController()
    @Published private(set) var activeEventIDs: Set<Int> = []
    @Published private(set) var isBusy = false
    @Published private(set) var status: String?
    @Published private(set) var isEnabled = false
    private let service: any GameActivityServing
    private let isForeground: () -> Bool
    private let now: () -> Date
    private var pendingSnapshot: (snapshot: GameActivitySnapshot, generation: Int)?
    private var pendingStops: Set<Int> = []
    private var pendingStale: [Int: Int] = [:]
    private var viewingEventID: Int?
    private var viewingGeneration = 0
    private struct ObservationFence {
        var score: Date?
        var probability: Date?
    }
    // Fences are delivery metadata, never clocks attached to an undated value.
    private var observationFences: [String: ObservationFence] = [:]

    convenience init() {
        self.init(service: SystemGameActivityService(),
                  isForeground: { UIApplication.shared.applicationState == .active })
    }
    init(service: any GameActivityServing, isForeground: @escaping () -> Bool,
         now: @escaping () -> Date = Date.init) {
        self.service = service
        self.isForeground = isForeground
        self.now = now
        reconcile()
    }

    func reconcile() {
        isEnabled = service.isEnabled
        let records = service.records
        activeEventIDs = Set(records.map(\.eventID))
        let activeIDs = Set(records.map(\.id))
        observationFences = observationFences.filter { activeIDs.contains($0.key) }
        for record in records { rememberClocks(record.snapshot, id: record.id) }
    }

    func beginViewing(eventID: Int) {
        guard isForeground(), eventID > 0 else { return }
        if viewingEventID != eventID {
            viewingGeneration += 1
            viewingEventID = eventID
            pendingSnapshot = nil
        }
    }

    /// Invalidate synchronously, before a view's asynchronous teardown can race
    /// with a queued update. A later appearance must acquire a new generation.
    func endViewing(eventID: Int) {
        guard viewingEventID == eventID else { return }
        let generation = invalidateViewing(eventID: eventID)
        Task { await self.applyStale(eventID: eventID, generation: generation) }
    }

    func start(snapshot: GameActivitySnapshot) {
        guard !isBusy else { return }
        reconcile()
        guard isForeground() else { status = "Open the app to start a Live Activity."; return }
        guard isEnabled else { status = "Live Activities are unavailable or disabled in Settings."; return }
        guard snapshot.eventID > 0, !snapshot.isTerminal else {
            status = "A finished or unavailable game cannot start a Live Activity."
            return
        }
        guard service.records.isEmpty else {
            status = activeEventIDs == [snapshot.eventID]
                ? "This game already has a Live Activity."
                : "Stop the existing game's Live Activity before starting this game."
            return
        }
        do {
            try service.request(snapshot, staleDate: staleDate(for: snapshot))
            beginViewing(eventID: snapshot.eventID)
            status = "Live Activity started. Updates arrive while this game is open."
        } catch {
            status = "Couldn't start the Live Activity. Try again."
        }
        reconcile()
    }

    func update(snapshot: GameActivitySnapshot) async {
        await update(snapshot: snapshot, generation: viewingGeneration)
    }

    private func update(snapshot: GameActivitySnapshot, generation: Int) async {
        guard eligible(eventID: snapshot.eventID, generation: generation), !Task.isCancelled else { return }
        reconcile()
        let matches = service.records.filter { $0.eventID == snapshot.eventID }
        guard !matches.isEmpty else { return }
        if isBusy {
            guard matches.contains(where: {
                canAdopt(snapshot, after: $0.snapshot, fence: observationFences[$0.id])
            }) else { return }
            if pendingSnapshot.map({ canAdopt(snapshot, after: $0.snapshot) }) ?? true {
                pendingSnapshot = (snapshot, generation)
                for record in matches { rememberClocks(snapshot, id: record.id) }
            }
            return
        }
        isBusy = true
        for record in matches {
            guard !Task.isCancelled, eligible(eventID: snapshot.eventID, generation: generation),
                  canAdopt(snapshot, after: record.snapshot, fence: observationFences[record.id]) else { continue }
            rememberClocks(snapshot, id: record.id)
            if snapshot.isTerminal {
                await service.end(id: record.id, final: snapshot)
                status = "Game finished. The Live Activity has ended."
            } else {
                await service.update(id: record.id, snapshot: snapshot, staleDate: staleDate(for: snapshot))
            }
        }
        await finishOperation()
    }

    func stop(eventID: Int) async {
        if pendingSnapshot?.snapshot.eventID == eventID { pendingSnapshot = nil }
        if isBusy { pendingStops.insert(eventID); return }
        isBusy = true
        for record in service.records where record.eventID == eventID {
            await service.end(id: record.id, final: nil)
        }
        status = "Live Activity stopped."
        await finishOperation()
    }

    /// Suspension never implies that a later server update will arrive.
    func markStale(eventID: Int) async {
        let generation = invalidateViewing(eventID: eventID)
        await applyStale(eventID: eventID, generation: generation)
    }

    private func invalidateViewing(eventID: Int) -> Int {
        if viewingEventID == eventID {
            viewingGeneration += 1
            viewingEventID = nil
        }
        if pendingSnapshot?.snapshot.eventID == eventID { pendingSnapshot = nil }
        return viewingGeneration
    }

    private func applyStale(eventID: Int, generation: Int) async {
        guard viewingEventID != eventID else { return }
        if isBusy { pendingStale[eventID] = generation; return }
        isBusy = true
        for record in service.records where record.eventID == eventID {
            await service.update(id: record.id, snapshot: record.snapshot, staleDate: now())
        }
        await finishOperation()
    }

    private func finishOperation() async {
        isBusy = false
        reconcile()
        if let id = pendingStops.first {
            pendingStops.remove(id)
            await stop(eventID: id)
        } else if let (id, generation) = pendingStale.first {
            pendingStale.removeValue(forKey: id)
            if viewingEventID != id {
                await applyStale(eventID: id, generation: generation)
            } else { await finishOperation() }
        } else if let pending = pendingSnapshot {
            pendingSnapshot = nil
            // A newer caller's update must not inherit the superseded caller's
            // cancellation (SwiftUI cancels tasks when the snapshot changes).
            Task { await self.update(snapshot: pending.snapshot, generation: pending.generation) }
        }
    }

    private func eligible(eventID: Int, generation: Int) -> Bool {
        isForeground() && viewingEventID == eventID && viewingGeneration == generation
    }

    private func rememberClocks(_ snapshot: GameActivitySnapshot, id: String) {
        var fence = observationFences[id] ?? ObservationFence()
        if let clock = snapshot.scoreObservedAt, fence.score.map({ clock > $0 }) ?? true { fence.score = clock }
        if let clock = snapshot.probabilityObservedAt, fence.probability.map({ clock > $0 }) ?? true { fence.probability = clock }
        observationFences[id] = fence
    }

    private func staleDate(for snapshot: GameActivitySnapshot) -> Date {
        let current = now()
        var clocks: [Date] = []
        if snapshot.homeScore != nil || snapshot.awayScore != nil {
            guard let clock = snapshot.scoreObservedAt else { return current }
            clocks.append(clock)
        }
        if snapshot.homeRenderedPercent != nil {
            guard let clock = snapshot.probabilityObservedAt else { return current }
            clocks.append(clock)
        }
        guard let oldest = clocks.min(), oldest <= current else { return current }
        return oldest.addingTimeInterval(120)
    }

    private func canAdopt(_ candidate: GameActivitySnapshot, after previous: GameActivitySnapshot,
                          fence: ObservationFence? = nil) -> Bool {
        guard candidate.eventID == previous.eventID else { return false }
        guard !previous.isTerminal || candidate.isTerminal else { return false }
        // Terminal lifecycle authority wins over price/score delivery age. Keep
        // the final's real clock even when it is older; never fabricate a newer one.
        if candidate.isTerminal { return true }
        for (before, after) in [(fence?.score ?? previous.scoreObservedAt, candidate.scoreObservedAt),
                                (fence?.probability ?? previous.probabilityObservedAt, candidate.probabilityObservedAt)] {
            if let before, let after, after < before { return false }
        }
        return true
    }
}
#endif
