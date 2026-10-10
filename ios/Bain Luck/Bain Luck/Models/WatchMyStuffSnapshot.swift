import Foundation

/// Shared wire contract. Contains display identities only, never an account ID or token.
nonisolated struct WatchMyStuffSnapshot: Codable, Equatable, Sendable {
    static let contextKey = "watch_my_stuff_v1"
    static let handshakeKey = "watch_my_stuff_handshake_v1"
    static let maxBytes = 48 * 1024
    static let maxItems = 48
    static let maxSessionAge: TimeInterval = 24 * 60 * 60
    let version: Int
    let publisher: UUID
    let generation: Int
    let revision: Int
    let sampledAt: Date
    let validUntil: Date
    let account: Account
    var pins: Section
    var teams: Section

    enum Account: String, Codable, Sendable { case signedOut, connecting, signedIn }
    enum State: String, Codable, Sendable { case loading, loaded, pending, failed }
    struct Item: Codable, Equatable, Identifiable, Sendable {
        let kind: String // event, future, team; retain unsupported types for phone recovery.
        let targetID: Int
        let relation: String?
        var title: String
        var unavailable: Bool = false
        var id: String { "\(kind):\(targetID):\(relation ?? "")" }
        var relationLabel: String? {
            switch relation {
            case "follow": return "Following"
            case "local": return "Local team"
            case "alma_mater": return "Alma mater"
            case "rival": return "Rival"
            case .some: return "Saved team"
            case .none: return nil
            }
        }
    }
    struct Section: Codable, Equatable, Sendable {
        var state: State = .loading
        var items: [Item] = []
        var syncedAt: Date?
        var omittedCount: Int = 0
    }

    func valid(at now: Date) -> Bool {
        guard version == 1, generation >= 0, revision > 0,
              sampledAt.timeIntervalSince1970.isFinite, validUntil.timeIntervalSince1970.isFinite,
              sampledAt <= now.addingTimeInterval(300),
              validUntil <= sampledAt.addingTimeInterval(Self.maxSessionAge) else { return false }
        if account != .signedIn {
            return pins.items.isEmpty && teams.items.isEmpty
        }
        guard validUntil > now else { return false }
        return [pins, teams].allSatisfy { section in
            section.items.count <= Self.maxItems && section.omittedCount >= 0
            && Set(section.items.map(\.id)).count == section.items.count
            && section.items.allSatisfy {
                $0.targetID > 0 && !$0.kind.isEmpty && $0.kind.utf8.count <= 32
                && $0.title.utf8.count <= 2048 && ($0.relation?.utf8.count ?? 0) <= 64
            }
            && (section.syncedAt.map { $0.timeIntervalSince1970.isFinite && $0 <= sampledAt } ?? true)
        }
    }

    static func decode(_ data: Data, now: Date) -> Self? {
        guard data.count <= maxBytes, let value = try? JSONDecoder().decode(Self.self, from: data),
              value.valid(at: now) else { return nil }
        return value
    }
}

/// Persistent high-water mark survives cache expiry and tombstones. Only a reply
/// to the current nonce can establish a new phone publisher after reinstall.
nonisolated struct WatchMyStuffCursor: Codable, Equatable, Sendable {
    var publisher: UUID?
    var generation = -1
    var revision = 0

    mutating func accept(_ snapshot: WatchMyStuffSnapshot, pairedHandshake: Bool) -> Bool {
        if publisher != snapshot.publisher {
            guard pairedHandshake else { return false }
        } else {
            guard snapshot.generation >= generation, snapshot.revision > revision else { return false }
        }
        publisher = snapshot.publisher
        generation = snapshot.generation
        revision = snapshot.revision
        return true
    }
}
