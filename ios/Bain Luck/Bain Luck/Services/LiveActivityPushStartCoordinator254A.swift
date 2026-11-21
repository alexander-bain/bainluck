#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import Foundation
import SwiftUI

/// #13052 / Rulings 177: A, 178: B, 254: A — registers the phone's ActivityKit push-to-start token
/// and current pins with `PUT /api/devices/{device_id}` (no account required), claims the device on
/// sign-in (`POST /api/devices/{device_id}/claim`), and observes push-started Live Activities so
/// their per-activity update push tokens register under `X-Device-Id` + `X-Device-Secret`.
@MainActor final class LiveActivityPushStartCoordinator254A {
    static let shared = LiveActivityPushStartCoordinator254A()

    private final class ActivityTrack {
        let eventID: Int
        var version: Int = 0
        var lastRegisteredToken: String?
        var revoked = false
        var tokenTask: Task<Void, Never>?
        var stateTask: Task<Void, Never>?

        init(eventID: Int) {
            self.eventID = eventID
        }
    }

    private let identityStore: any DeviceIdentityStoring254A
    private let transport: any PushDeviceTransport254A
    private let apnsEnv: String
    private let osMajor: Int
    private let appVersion: String?

    private var identity: DeviceIdentity254A?
    private var laStartToken: String?
    private var pinnedEventIDs: [Int] = []
    private var pinnedMarketIDs: [Int] = []
    private var lastSyncedState: PushDeviceState254A?
    private var hasSyncedOnce = false
    private var sessionBearer: String?
    private var claimedBearer: String?
    private var started = false
    private var startTokenTask: Task<Void, Never>?
    private var activityUpdatesTask: Task<Void, Never>?
    private var trackedActivities: [String: ActivityTrack] = [:]

    convenience init() {
        self.init(
            identityStore: KeychainDeviceIdentityStore254A.shared,
            transport: PushDeviceClient254A()
        )
    }

    init(
        identityStore: any DeviceIdentityStoring254A,
        transport: any PushDeviceTransport254A,
        apnsEnv: String = PushDeviceState254A.defaultAPNsEnvironment,
        osMajor: Int = ProcessInfo.processInfo.operatingSystemVersion.majorVersion,
        appVersion: String? = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    ) {
        self.identityStore = identityStore
        self.transport = transport
        self.apnsEnv = apnsEnv
        self.osMajor = osMajor
        self.appVersion = appVersion
    }

    /// True if this coordinator has registered an active push-started Live Activity on this phone.
    func hasDeviceRegisteredActivity(eventID: Int) -> Bool {
        trackedActivities.values.contains { !$0.revoked && $0.eventID == eventID && $0.lastRegisteredToken != nil }
    }

    var hasAnyDeviceRegisteredActivity: Bool {
        trackedActivities.values.contains { !$0.revoked && $0.lastRegisteredToken != nil }
    }

    func start() {
        guard !started else { return }
        started = true
        _ = resolveIdentity()

        if #available(iOS 17.2, *) {
            if let existing = Activity<GameActivityAttributes>.pushToStartToken {
                Task { await receiveStartToken(existing) }
            }
            startTokenTask = Task { [weak self] in
                for await token in Activity<GameActivityAttributes>.pushToStartTokenUpdates {
                    guard !Task.isCancelled else { break }
                    await self?.receiveStartToken(token)
                }
            }
        }

        // Observe existing and future push-started Live Activities so their update tokens register
        // with the server using `X-Device-Id` + `X-Device-Secret` (works signed out or signed in).
        for activity in Activity<GameActivityAttributes>.activities {
            observeSystemActivity(activity)
        }
        activityUpdatesTask = Task { [weak self] in
            for await activity in Activity<GameActivityAttributes>.activityUpdates {
                guard !Task.isCancelled else { break }
                self?.observeSystemActivity(activity)
            }
        }
    }

    func updatePins(eventIDs: Set<Int>, marketIDs: Set<Int>) async {
        pinnedEventIDs = PushDeviceState254A.normalizePinIDs(Array(eventIDs))
        pinnedMarketIDs = PushDeviceState254A.normalizePinIDs(Array(marketIDs))
        await syncDeviceIfNeeded()
    }

    func receiveStartToken(_ tokenData: Data) async {
        let hex = PushDeviceState254A.hexToken(from: tokenData)
        guard !hex.isEmpty else { return }
        laStartToken = hex
        await syncDeviceIfNeeded()
    }

    func updateSession(bearer: String?) async {
        let clean = bearer?.isEmpty == false ? bearer : nil
        sessionBearer = clean
        if clean == nil {
            claimedBearer = nil
            return
        }
        await claimIfReady()
    }

    func foregroundActivated() async {
        await syncDeviceIfNeeded()
        await claimIfReady()
    }

    /// Directly testable hook for registering an update push token on a push-started Live Activity.
    func registerPushStartedActivityToken(id: String, eventID: Int, tokenData: Data) async {
        let hex = PushDeviceState254A.hexToken(from: tokenData)
        guard !hex.isEmpty, eventID > 0 else { return }
        // Ensure the parent `push_devices` row exists before referencing it via `X-Device-Id`.
        if !hasSyncedOnce {
            await syncDeviceIfNeeded(forceEvenWithoutStartToken: true)
        }
        let track = trackedActivities[id] ?? {
            let created = ActivityTrack(eventID: eventID)
            trackedActivities[id] = created
            return created
        }()
        guard !track.revoked, track.lastRegisteredToken != hex else { return }
        let idCred = resolveIdentity()

        do {
            let meta = try await transport.mutateActivityRegistration(
                id: id,
                eventID: eventID,
                token: hex,
                version: track.version,
                mutationID: UUID(),
                identity: idCred
            )
            track.version = meta.version
            track.lastRegisteredToken = hex
        } catch PushDeviceClientError254A.conflict {
            // Reconcile server version once and retry PUT.
            if let current = try? await transport.readActivityRegistration(id: id, identity: idCred),
               current.isActive, current.eventID == eventID {
                track.version = current.version
                if let meta = try? await transport.mutateActivityRegistration(
                    id: id,
                    eventID: eventID,
                    token: hex,
                    version: track.version,
                    mutationID: UUID(),
                    identity: idCred
                ) {
                    track.version = meta.version
                    track.lastRegisteredToken = hex
                }
            }
        } catch {
            // Non-fatal: will retry on next token emission or foreground activation.
        }
    }

    /// Directly testable hook for revoking a device-owned Live Activity registration when ended.
    func revokePushStartedActivity(id: String, eventID: Int) async {
        guard let track = trackedActivities[id], !track.revoked else { return }
        track.revoked = true
        track.tokenTask?.cancel()
        track.stateTask?.cancel()
        let idCred = resolveIdentity()
        do {
            let meta = try await transport.mutateActivityRegistration(
                id: id,
                eventID: eventID,
                token: nil,
                version: track.version,
                mutationID: UUID(),
                identity: idCred
            )
            track.version = meta.version
        } catch PushDeviceClientError254A.conflict {
            if let current = try? await transport.readActivityRegistration(id: id, identity: idCred),
               current.isActive, current.eventID == eventID {
                _ = try? await transport.mutateActivityRegistration(
                    id: id,
                    eventID: eventID,
                    token: nil,
                    version: current.version,
                    mutationID: UUID(),
                    identity: idCred
                )
            }
        } catch {
            // Best-effort revocation; server registration also carries a bounded horizon.
        }
    }

    // MARK: - Private helpers

    private func resolveIdentity() -> DeviceIdentity254A {
        if let identity { return identity }
        let loaded = identityStore.loadOrCreate()
        identity = loaded
        return loaded
    }

    private func observeSystemActivity(_ activity: Activity<GameActivityAttributes>) {
        guard trackedActivities[activity.id] == nil else { return }
        // Avoid double-registering signed-in foreground activities already owned by `GameActivityRegistrationCoordinator`.
        guard !GameActivityRegistrationCoordinator.shared.isAccountOwned(id: activity.id) else { return }
        let track = ActivityTrack(eventID: activity.attributes.eventID)
        trackedActivities[activity.id] = track

        if let token = activity.pushToken {
            Task { [weak self] in
                await self?.registerPushStartedActivityToken(
                    id: activity.id,
                    eventID: activity.attributes.eventID,
                    tokenData: token
                )
            }
        }
        track.tokenTask = Task { [weak self] in
            for await token in activity.pushTokenUpdates {
                guard !Task.isCancelled else { break }
                await self?.registerPushStartedActivityToken(
                    id: activity.id,
                    eventID: activity.attributes.eventID,
                    tokenData: token
                )
            }
        }
        track.stateTask = Task { [weak self] in
            for await state in activity.activityStateUpdates {
                guard !Task.isCancelled else { break }
                if state == .ended || state == .dismissed {
                    await self?.revokePushStartedActivity(
                        id: activity.id,
                        eventID: activity.attributes.eventID
                    )
                    break
                }
            }
        }
    }

    private func syncDeviceIfNeeded(forceEvenWithoutStartToken: Bool = false) async {
        // Don't create empty rows on devices with no push-to-start token until one is issued
        // (unless we already synced once or need the row to own a push-started Live Activity).
        guard laStartToken != nil || hasSyncedOnce || forceEvenWithoutStartToken else { return }
        let state = PushDeviceState254A(
            platform: "ios",
            apnsEnv: apnsEnv,
            laStartToken: laStartToken,
            osMajor: osMajor,
            appVersion: appVersion,
            pinnedEventIDs: pinnedEventIDs,
            pinnedMarketIDs: pinnedMarketIDs
        )
        guard state != lastSyncedState else { return }
        let idCred = resolveIdentity()
        do {
            try await transport.putDevice(identity: idCred, state: state)
            lastSyncedState = state
            hasSyncedOnce = true
            await claimIfReady()
        } catch {
            // Keep `lastSyncedState` unchanged so the next pin change or activation retries cleanly.
        }
    }

    private func claimIfReady() async {
        guard hasSyncedOnce, let bearer = sessionBearer, bearer != claimedBearer else { return }
        let idCred = resolveIdentity()
        do {
            try await transport.claimDevice(identity: idCred, bearer: bearer)
            claimedBearer = bearer
        } catch {
            // Retry on next foreground activation or sync.
        }
    }
}

private struct LiveActivityPushStartModifier254A: ViewModifier {
    @ObservedObject var pins: PinManager

    func body(content: Content) -> some View {
        content
            .task {
                LiveActivityPushStartCoordinator254A.shared.start()
                await LiveActivityPushStartCoordinator254A.shared.updatePins(
                    eventIDs: pins.pinnedEventIDs,
                    marketIDs: pins.pinnedFuturesIDs
                )
            }
            .onChange(of: pins.pinnedEventIDs) { _, events in
                let markets = pins.pinnedFuturesIDs
                Task {
                    await LiveActivityPushStartCoordinator254A.shared.updatePins(
                        eventIDs: events,
                        marketIDs: markets
                    )
                }
            }
            .onChange(of: pins.pinnedFuturesIDs) { _, markets in
                let events = pins.pinnedEventIDs
                Task {
                    await LiveActivityPushStartCoordinator254A.shared.updatePins(
                        eventIDs: events,
                        marketIDs: markets
                    )
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: UIScene.didActivateNotification)) { _ in
                Task {
                    await LiveActivityPushStartCoordinator254A.shared.foregroundActivated()
                }
            }
    }
}

extension View {
    func liveActivityPushStart254A(pins: PinManager) -> some View {
        modifier(LiveActivityPushStartModifier254A(pins: pins))
    }
}
#endif
