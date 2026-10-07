import Foundation

/// Typed local diagnostics. No SDK, network, identifiers or user-written strings.
/// The runtime may collect only after explicit Watch consent AND a current phone
/// grant. The phone must independently validate its consent epoch before emission.
nonisolated enum WatchTelemetrySurface: String, Codable, CaseIterable, Sendable {
    case game = "watch_game", picker = "watch_picker"
    case discoveries = "watch_discoveries", diagnostics = "watch_diagnostics"
}

nonisolated enum WatchTelemetryKind: String, Codable, CaseIterable, Sendable {
    case appOpen = "watch_app_open", appBackground = "watch_app_background"
    case screen = "screen_view", timing = "screen_timing"
    case action = "watch_action", refresh = "watch_refresh", reading = "watch_reading"
}

nonisolated enum WatchTelemetryAction: String, Codable, CaseIterable, Sendable {
    case chooseGame = "choose_game", selectGame = "select_game", reselectGame = "reselect_game"
    case clearGame = "clear_game", refresh, discoveries, close
    case phoneContinuation = "phone_continuation_help", dismissHelp = "dismiss_help"
    case complicationOpen = "complication_open"
}

nonisolated enum WatchTelemetryOutcome: String, Codable, CaseIterable, Sendable {
    case success, failure, cancelled, empty, offline, timeout, busy, unknown, saved, fresh
}

/// UUID is a per-event acknowledgement key, never sent to Analytics.
nonisolated struct WatchTelemetryRecord: Codable, Equatable, Sendable {
    let id: UUID
    let recordedAt: Date
    let kind: WatchTelemetryKind
    let surface: WatchTelemetrySurface
    let action: WatchTelemetryAction?
    let outcome: WatchTelemetryOutcome?
    let durationMS: Int?
    let firstCardMS: Int?
    let count: Int?
    let cold: Bool?
    let appBuild: String

    init(id: UUID = UUID(), recordedAt: Date, kind: WatchTelemetryKind,
         surface: WatchTelemetrySurface, action: WatchTelemetryAction? = nil,
         outcome: WatchTelemetryOutcome? = nil, durationMS: Int? = nil,
         firstCardMS: Int? = nil, count: Int? = nil, cold: Bool? = nil, appBuild: String = "unknown") {
        self.id = id; self.recordedAt = recordedAt; self.kind = kind; self.surface = surface
        self.action = action; self.outcome = outcome; self.durationMS = durationMS
        self.firstCardMS = firstCardMS; self.count = count; self.cold = cold
        self.appBuild = appBuild
    }

    /// Validation is also applied after decoding; Codable alone is not a trust boundary.
    var isWellFormed: Bool {
        guard (appBuild == "unknown" || (!appBuild.isEmpty && appBuild.utf8.count <= 64
                && appBuild.unicodeScalars.allSatisfy { "0123456789. ()".unicodeScalars.contains($0) })),
              recordedAt.timeIntervalSince1970.isFinite,
              durationMS.map({ (0...3_600_000).contains($0) }) ?? true,
              firstCardMS.map({ (-1...3_600_000).contains($0) }) ?? true,
              count.map({ (0...100).contains($0) }) ?? true else { return false }
        switch kind {
        case .action: return action != nil && outcome == nil && firstCardMS == nil
        case .refresh: return action == nil && outcome != nil && durationMS != nil && firstCardMS == nil
        case .timing: return action == nil && firstCardMS != nil && cold != nil && outcome != nil
        case .reading: return action == nil && outcome != nil && firstCardMS == nil
        case .appOpen, .appBackground, .screen:
            return action == nil && outcome == nil && firstCardMS == nil
        }
    }
}

nonisolated struct WatchTelemetryGrant: Codable, Equatable, Sendable {
    let epoch: UUID
    let validUntil: Date
    func permits(at now: Date) -> Bool {
        now.timeIntervalSince1970.isFinite && validUntil.timeIntervalSince1970.isFinite
            && validUntil > now && validUntil.timeIntervalSince(now) <= WatchTelemetryBuffer.maxAge + WatchTelemetryBuffer.clockSkewTolerance
    }
}

nonisolated struct WatchTelemetryBatch: Codable, Sendable {
    let schema: Int
    let phoneEpoch: UUID
    let watchEpoch: UUID
    let records: [WatchTelemetryRecord]
}

/// An explicit Watch grant does not infer or enable phone consent. Persist this
/// snapshot atomically from the runtime; failure to persist never means consent saved.
nonisolated struct WatchTelemetryBuffer: Codable, Sendable {
    static let maxCount = 64
    static let maxBytes = 48 * 1024
    static let maxBatchBytes = 12 * 1024
    static let maxAge: TimeInterval = 24 * 60 * 60
    static let clockSkewTolerance: TimeInterval = 300
    private(set) var watchEpoch: UUID?
    private(set) var phoneGrant: WatchTelemetryGrant?
    private(set) var records: [WatchTelemetryRecord] = []

    mutating func setWatchConsent(_ granted: Bool) {
        if granted {
            if watchEpoch == nil { watchEpoch = UUID() }
        } else {
            watchEpoch = nil
            phoneGrant = nil
            records.removeAll()
        }
    }

    mutating func setPhoneGrant(_ grant: WatchTelemetryGrant?, now: Date) {
        let permitted = grant.flatMap { $0.permits(at: now) ? $0 : nil }
        if phoneGrant?.epoch != permitted?.epoch { records.removeAll() }
        phoneGrant = permitted
        prune(now: now)
    }

    mutating func append(_ record: WatchTelemetryRecord, now: Date) {
        prune(now: now)
        guard watchEpoch != nil, phoneGrant?.permits(at: now) == true,
              record.isWellFormed, Self.isCurrent(record, now: now),
              !records.contains(where: { $0.id == record.id }) else { return }
        records.append(record)
        enforceBounds()
    }

    mutating func batch(now: Date) -> WatchTelemetryBatch? {
        prune(now: now)
        guard let watchEpoch, let phoneGrant, !records.isEmpty else { return nil }
        var selected: [WatchTelemetryRecord] = []
        for record in records.prefix(12) {
            let next = WatchTelemetryBatch(schema: 1, phoneEpoch: phoneGrant.epoch,
                                          watchEpoch: watchEpoch, records: selected + [record])
            guard let bytes = try? JSONEncoder().encode(next), bytes.count <= Self.maxBatchBytes else { break }
            selected.append(record)
        }
        guard !selected.isEmpty else { return nil }
        return WatchTelemetryBatch(schema: 1, phoneEpoch: phoneGrant.epoch,
                                   watchEpoch: watchEpoch, records: selected)
    }

    mutating func acknowledge(_ ids: Set<UUID>, phoneEpoch: UUID, watchEpoch: UUID) {
        // A delayed reply from an earlier consent generation cannot drain a new queue.
        guard self.watchEpoch == watchEpoch, phoneGrant?.epoch == phoneEpoch else { return }
        records.removeAll { ids.contains($0.id) }
    }

    mutating func prune(now: Date) {
        guard watchEpoch != nil, phoneGrant?.permits(at: now) == true else {
            records.removeAll()
            phoneGrant = nil
            return
        }
        records.removeAll { !$0.isWellFormed || !Self.isCurrent($0, now: now) }
        var seen = Set<UUID>()
        records = records.filter { seen.insert($0.id).inserted }
        enforceBounds()
    }

    static func restore(_ data: Data?, now: Date) -> Self {
        guard let data, data.count <= maxBytes,
              var state = try? JSONDecoder().decode(Self.self, from: data) else { return Self() }
        state.prune(now: now)
        return state
    }

    private static func isCurrent(_ record: WatchTelemetryRecord, now: Date) -> Bool {
        let age = now.timeIntervalSince(record.recordedAt)
        return age.isFinite && age >= -Self.clockSkewTolerance && age < Self.maxAge
    }

    private mutating func enforceBounds() {
        if records.count > Self.maxCount { records.removeFirst(records.count - Self.maxCount) }
        while !records.isEmpty {
            guard let bytes = try? JSONEncoder().encode(self), bytes.count <= Self.maxBytes else {
                records.removeFirst(); continue
            }
            break
        }
    }
}

/// Validate the actual wire before any Analytics call. Unknown Codable enum
/// values reject the packet; unrecognized JSON fields never enter parameters.
nonisolated enum WatchTelemetryIngress {
    nonisolated struct Accepted: Sendable {
        let acknowledgement: [UUID]
        let records: [WatchTelemetryRecord]
    }

    static func accept(_ data: Data, phoneEpoch: UUID?, now: Date,
                       seen: Set<UUID>) -> Accepted {
        let empty = Accepted(acknowledgement: [], records: [])
        guard data.count <= WatchTelemetryBuffer.maxBatchBytes,
              let phoneEpoch, now.timeIntervalSince1970.isFinite,
              let batch = try? JSONDecoder().decode(WatchTelemetryBatch.self, from: data),
              batch.schema == 1, batch.phoneEpoch == phoneEpoch,
              !batch.records.isEmpty, batch.records.count <= 12 else { return empty }
        var ids = Set<UUID>()
        var records: [WatchTelemetryRecord] = []
        for record in batch.records {
            guard ids.insert(record.id).inserted else { continue }
            let age = now.timeIntervalSince(record.recordedAt)
            guard record.isWellFormed, age.isFinite, age >= -WatchTelemetryBuffer.clockSkewTolerance,
                  age < WatchTelemetryBuffer.maxAge, !seen.contains(record.id) else { continue }
            records.append(record)
        }
        // Invalid/expired records are acknowledged for disposal, never emitted.
        return Accepted(acknowledgement: Array(ids), records: records)
    }
}

extension WatchTelemetryRecord {
    /// All strings originate in fixed enums. The UUID and original timestamp
    /// are for local queue/ack validation and never become Analytics identity.
    var analyticsParameters: [String: Any] {
        var result: [String: Any] = ["surface": surface.rawValue, "device_class": "watch", "app_build": appBuild]
        if kind == .screen { result["screen_name"] = surface.rawValue; result["page_type"] = "watch" }
        if let action { result["action"] = action.rawValue }
        if let outcome { result["outcome_class"] = outcome.rawValue }
        if let count { result["card_count"] = count }
        if let durationMS { result["duration_ms"] = durationMS }
        if let firstCardMS {
            result["first_card_ms"] = firstCardMS
            // These visual milestones are not measured by SwiftUI callbacks.
            result["shell_ms"] = -1; result["fold_ms"] = -1; result["interactive_ms"] = -1
            result["network_class"] = "unknown"
        }
        if let cold { result["entry"] = cold ? "cold" : "warm" }
        return result
    }
}


/// Multiple SwiftUI callbacks may observe the same reading in one update.
/// Stored only in memory; never includes a game or account identifier.
nonisolated struct WatchTelemetryReadingTracker {
    private struct Reading: Equatable {
        let fetchedAt: Date
        let saved: Bool
    }
    private var last: [WatchTelemetrySurface: Reading] = [:]

    mutating func accept(_ surface: WatchTelemetrySurface, fetchedAt: Date?, saved: Bool) -> Bool {
        guard let fetchedAt, fetchedAt.timeIntervalSince1970.isFinite else { return false }
        let reading = Reading(fetchedAt: fetchedAt, saved: saved)
        guard last[surface] != reading else { return false }
        last[surface] = reading
        return true
    }

    mutating func reset() { last.removeAll() }
}
