#if DEBUG
import Combine
import Foundation
import SwiftUI

/// A pin-only controlled transport/storage adapter for the original #9875 app
/// arms. AuthManager stays real. All mutations go to this unique defaults suite;
/// none of these closures calls APIClient. The production PinManager and views
/// perform the actual save, rollback, persistence, presentation and generation work.
final class PinManagementRuntime9875: ObservableObject {
    nonisolated struct Configuration: Equatable, Sendable {
        let suite: String
        let seed: Bool
        let offline: Bool
    }
    nonisolated enum Failure: Error, Equatable, Sendable {
        case harness(String), offline, rejected
    }
    nonisolated enum Slot: String, Sendable { case a = "A", b = "B", guest, unresolved }
    nonisolated enum Reply: String, Sendable { case confirm, fail, hold }
    nonisolated struct SyncCall: Sendable {
        let slot: Slot
        let type: String
        let id: Int
        let pinned: Bool
    }
    private struct PendingSync {
        let call: SyncCall
        let continuation: CheckedContinuation<Void, Error>
    }
    private struct PendingLoad {
        let pins: PinsResponse
        let continuation: CheckedContinuation<PinsResponse, Error>
    }
    private struct PendingMetadata {
        let pin: SavedPin
        let slot: Slot
        let continuation: CheckedContinuation<PinMetadata, Never>
    }

    static let shared: PinManagementRuntime9875? = {
        LaunchRig.pinRuntime9875().map { PinManagementRuntime9875(configuration: $0) }
    }()
    static let detailID = 15319563 // Existing #9495 real, read-only detail specimen.
    let configuration: Configuration
    let defaults: UserDefaults
    @Published private(set) var failure: Failure?
    @Published private(set) var realIdentity = PinAccountBinding(userID: nil, authenticated: false)
    @Published private(set) var slot: Slot = .a
    @Published private(set) var seedState = "not_requested"
    @Published private(set) var calls: [SyncCall] = []
    @Published private(set) var heldSyncCount = 0
    @Published private(set) var heldMetadataCount = 0
    @Published private(set) var heldLoadCount = 0
    @Published var nextReply: Reply = .confirm
    @Published var offline: Bool
    @Published var holdMetadata = false
    @Published var holdNextLoad = false
    private var pendingSync: [PendingSync] = []
    private var pendingMetadata: [PendingMetadata] = []
    private var pendingLoads: [PendingLoad] = []

    init(configuration result: Result<Configuration, Failure>) {
        let config: Configuration
        let initialFailure: Failure?
        switch result {
        case .success(let value): config = value; initialFailure = nil
        case .failure(let error):
            config = Configuration(suite: "bainluck.debug.9875.\(UUID())", seed: false, offline: true)
            initialFailure = error
        }
        self.configuration = config
        defaults = UserDefaults(suiteName: config.suite)!
        offline = config.offline
        failure = initialFailure
        if defaults.bool(forKey: "fixture.seeded") {
            seedState = "retained"
        } else if configuration.seed, failure == nil {
            for slot in [Slot.a, .b] {
                defaults.set(Self.initialEvents(slot), forKey: serverKey(slot, "event"))
                defaults.set(Self.initialMarkets(slot), forKey: serverKey(slot, "future"))
            }
            defaults.set(true, forKey: "fixture.seeded")
            seedState = "seeded"
        } else if failure == nil { failure = .harness("unseeded isolated pin store") }
        if let word = defaults.string(forKey: "driver.slot") {
            if let savedSlot = Slot(rawValue: word) { slot = savedSlot }
            else { failure = .harness("invalid retained fixture binding") }
        }
        if failure == nil {
            for owner in [Slot.a, .b] {
                for type in ["event", "future"] {
                    guard let ids = defaults.array(forKey: serverKey(owner, type)) as? [Int],
                          Set(ids).count == ids.count, ids.allSatisfy({ $0 > 0 }) else {
                        failure = .harness("missing or malformed retained fake server IDs")
                        continue
                    }
                }
            }
        }
    }

    nonisolated static func initialEvents(_ slot: Slot) -> [Int] {
        slot == .b ? [1, 201, 202, 203, 204, 205] : Array(1...6)
    }
    nonisolated static func initialMarkets(_ slot: Slot) -> [Int] {
        slot == .b ? Array(301...306) : Array(101...106)
    }
    private func serverKey(_ slot: Slot, _ type: String) -> String { "fixture.server.\(slot.rawValue).\(type)" }
    var ready: Bool { failure == nil && realIdentity.authenticated && realIdentity.userID != nil }

    func makeManager() -> PinManager {
        PinManager(defaults: defaults, allowLegacyGuestPins: false,
                   initialBinding: PinAccountBinding(userID: nil, authenticated: false),
                   serverLoad: { try await self.load() },
                   serverSync: { type, id, pinned in try await self.sync(type: type, id: id, pinned: pinned) })
    }

    /// Both normal app auth-binding sites and controlled A/B setup use this
    /// same production boundary. Only the pin binding is simulated; real auth
    /// remains observed and is never upgraded from false to true.
    func bindRealIdentity(_ identity: PinAccountBinding, to manager: PinManager) {
        if identity.authenticated, let principal = identity.userID {
            if let previous = defaults.string(forKey: "fixture.realPrincipal"), previous != principal {
                failure = .harness("actual restored principal changed; fixture cannot adopt another real account")
            } else if failure == nil { defaults.set(principal, forKey: "fixture.realPrincipal") }
        }
        realIdentity = identity
        applyBinding(to: manager)
    }
    func select(_ next: Slot, manager: PinManager) {
        guard ready else { return }
        slot = next
        defaults.set(next.rawValue, forKey: "driver.slot")
        applyBinding(to: manager)
        Task { await manager.loadPins() }
    }
    private func applyBinding(to manager: PinManager) {
        let binding: PinAccountBinding
        switch slot {
        case .a: binding = realIdentity
        case .b:
            binding = PinAccountBinding(userID: realIdentity.userID == nil ? nil : "DEBUG9875-B",
                                        authenticated: ready)
        case .guest: binding = PinAccountBinding(userID: nil, authenticated: false)
        case .unresolved: binding = PinAccountBinding(userID: realIdentity.userID, authenticated: false)
        }
        manager.bindAccount(binding)
    }

    @MainActor
    private func load() async throws -> PinsResponse {
        if let failure { throw failure }
        guard ready else { throw Failure.harness("actual restored sign-in required") }
        if offline { throw Failure.offline }
        let pins = PinsResponse(events: defaults.array(forKey: serverKey(slot, "event")) as? [Int] ?? [],
                                futures: defaults.array(forKey: serverKey(slot, "future")) as? [Int] ?? [])
        if holdNextLoad {
            holdNextLoad = false
            return try await withCheckedThrowingContinuation { continuation in
                pendingLoads.append(PendingLoad(pins: pins, continuation: continuation))
                heldLoadCount = pendingLoads.count
            }
        }
        return pins
    }
    func releaseLoads() {
        let replies = pendingLoads
        pendingLoads.removeAll()
        heldLoadCount = 0
        for pending in replies { pending.continuation.resume(returning: pending.pins) }
    }
    @MainActor
    private func sync(type: String, id: Int, pinned: Bool) async throws {
        if let failure { throw failure }
        guard ready, ["event", "future"].contains(type) else {
            throw Failure.harness("actual restored sign-in and pin type required")
        }
        let call = SyncCall(slot: slot, type: type, id: id, pinned: pinned)
        calls.append(call)
        let reply = nextReply
        nextReply = .confirm
        switch reply {
        case .confirm: confirm(call)
        case .fail: throw Failure.rejected
        case .hold:
            try await withCheckedThrowingContinuation { continuation in
                pendingSync.append(PendingSync(call: call, continuation: continuation))
                heldSyncCount = pendingSync.count
            }
        }
    }
    private func confirm(_ call: SyncCall) {
        let key = serverKey(call.slot, call.type)
        var ids = Set(defaults.array(forKey: key) as? [Int] ?? [])
        if call.pinned { ids.insert(call.id) } else { ids.remove(call.id) }
        defaults.set(ids.sorted(), forKey: key)
    }
    func releaseSync(confirm shouldConfirm: Bool) {
        let replies = pendingSync
        pendingSync.removeAll()
        heldSyncCount = 0
        for pending in replies {
            if shouldConfirm {
                confirm(pending.call) // Reply belongs to its dispatch slot, never B.
                pending.continuation.resume()
            } else { pending.continuation.resume(throwing: Failure.rejected) }
        }
    }

    @MainActor
    func lookup(_ pin: SavedPin) async -> PinMetadata {
        guard ready else { return .failed }
        let dispatchedSlot = slot
        if holdMetadata {
            return await withCheckedContinuation { continuation in
                pendingMetadata.append(PendingMetadata(pin: pin, slot: dispatchedSlot, continuation: continuation))
                heldMetadataCount = pendingMetadata.count
            }
        }
        return metadata(pin, slot: dispatchedSlot)
    }
    private func metadata(_ pin: SavedPin, slot: Slot) -> PinMetadata {
        if pin.value == 1 || pin.value == 101 { return .unavailable }
        if pin.value == 2 || pin.value == 102 { return .failed }
        return .available(title: "Fixture \(slot.rawValue) \(pin.type == "event" ? "game" : "market") \(pin.value)")
    }
    func releaseMetadata() {
        holdMetadata = false
        let replies = pendingMetadata
        pendingMetadata.removeAll()
        heldMetadataCount = 0
        for pending in replies { pending.continuation.resume(returning: metadata(pending.pin, slot: pending.slot)) }
    }

    func receipt(_ manager: PinManager) -> String {
        let keys = [realIdentity.userID, "DEBUG9875-B"].compactMap { $0 }
            .flatMap { ["bainluck_pins.user.\($0).Events", "bainluck_pins.user.\($0).Futures"] }
            + ["bainluck_pins.guest.Events", "bainluck_pins.guest.Futures"]
        let stores = Dictionary(uniqueKeysWithValues: keys.map { key -> (String, [Int]) in
            let ids = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode([Int].self, from: $0) } ?? []
            return (key, ids.sorted())
        })
        let value: [String: Any] = [
            "label": "CONTROLLED PIN BINDING / DEBUG / NOT PROVIDER ACCOUNT SWITCH",
            "suite": configuration.suite, "seed": seedState,
            "failure": failure.map { String(describing: $0) } ?? "",
            "real_signed_in": realIdentity.authenticated, "real_user_id": realIdentity.userID ?? "",
            "fixture_slot": slot.rawValue, "offline": offline,
            "load_state": String(describing: manager.loadState),
            "generation": manager.identityGeneration.uuidString,
            "saved": manager.savedPins.map(\.id), "saving": manager.savingKeys.sorted(),
            "held_sync": heldSyncCount, "held_metadata": heldMetadataCount, "held_load": heldLoadCount,
            "feedback": manager.feedback?.message ?? "", "stores": stores,
            "calls": calls.map { "\($0.slot.rawValue):\($0.type):\($0.id):\($0.pinned ? "add" : "remove")" }
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8) else { return "HARNESS: receipt encoding failed" }
        return text
    }
}

/// Shared between root and management sheets so held replies can be delivered
/// while the REAL list is presented. No control substitutes for a pin tap.
struct PinRuntime9875Controls: View {
    @ObservedObject var runtime: PinManagementRuntime9875
    @ObservedObject var manager: PinManager
    var body: some View {
        HStack(spacing: 6) {
            Text("CONTROLLED PINS 9875 · DEBUG")
                .font(.system(size: 8).monospaced())
                .accessibilityIdentifier("pin9875Receipt")
                .accessibilityValue(runtime.receipt(manager))
            Menu("9875 controls") {
                Button("Hold next reply") { runtime.nextReply = .hold }
                Button("Fail next reply") { runtime.nextReply = .fail }
                Button("Confirm next reply") { runtime.nextReply = .confirm }
                Button("Release reply success") { runtime.releaseSync(confirm: true) }
                Button("Release reply failure") { runtime.releaseSync(confirm: false) }
                Button("Hold pin refresh") { runtime.holdNextLoad = true; Task { await manager.loadPins() } }
                Button("Release pin refresh") { runtime.releaseLoads() }
                Button("Hold metadata") { runtime.holdMetadata = true }
                Button("Release metadata") { runtime.releaseMetadata() }
                Button("Fixture binding A") { runtime.select(.a, manager: manager) }
                Button("Fixture binding B") { runtime.select(.b, manager: manager) }
                Button("Fixture binding guest") { runtime.select(.guest, manager: manager) }
                Button("Fixture binding unresolved") { runtime.select(.unresolved, manager: manager) }
                Button("Offline pin load") { runtime.offline = true; Task { await manager.loadPins() } }
                Button("Online pin load") { runtime.offline = false; Task { await manager.loadPins() } }
            }
            .disabled(!runtime.ready)
            .accessibilityIdentifier("pin9875Controls")
        }
        .padding(4)
        .background(.regularMaterial)
    }
}

struct PinRuntime9875Setup: View {
    @ObservedObject var runtime: PinManagementRuntime9875
    @ObservedObject var manager: PinManager
    @ObservedObject var navigation: NavigationCoordinator
    @State private var detailSheet = false
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            PinRuntime9875Controls(runtime: runtime, manager: manager)
            HStack {
                Button("9875 stacked detail") {
                    navigation.navigate(to: .eventDetail(id: PinManagementRuntime9875.detailID), tab: .myStuff)
                }.accessibilityIdentifier("pin9875StackedDetail")
                Button("9875 sheet detail") {
                    navigation.selectedTab = .myStuff
                    detailSheet = true
                }.accessibilityIdentifier("pin9875SheetDetail")
            }
            .font(.caption2)
            .disabled(!runtime.ready)
        }
        .sheet(isPresented: $detailSheet) {
            NavigationStack {
                EventDetailView(eventId: PinManagementRuntime9875.detailID)
                    .toolbar { ToolbarItem(placement: .confirmationAction) {
                        Button("Close fixture detail") { detailSheet = false }
                    } }
            }
            .environmentObject(manager)
            .environmentObject(navigation)
        }
    }
}
#endif
