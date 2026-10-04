import Foundation

/// Public display-only snapshot. Shared access requires the entitled App Group container.
nonisolated struct WatchComplicationSnapshot: Codable, Sendable {
    static let filename = "selected-game.json"
    static let maximumBytes = 16 * 1024
    let version: Int
    let eventID: Int
    let title: String
    let detail: String
    let observedAt: Date
    let savedAt: Date

    init(version: Int = 1, eventID: Int, title: String, detail: String,
         observedAt: Date, savedAt: Date) {
        self.version = version
        self.eventID = eventID
        self.title = title
        self.detail = detail
        self.observedAt = observedAt
        self.savedAt = savedAt
    }

    func isValid(now: Date) -> Bool {
        let observation = observedAt.timeIntervalSinceReferenceDate
        let saved = savedAt.timeIntervalSinceReferenceDate
        let clock = now.timeIntervalSinceReferenceDate
        return version == 1 && eventID > 0
            && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && observation.isFinite && saved.isFinite && clock.isFinite
            && observation <= saved && saved <= clock
    }

    /// Never substitutes process-local defaults for an unavailable shared container.
    static func read(from directory: URL?, now: Date = Date()) -> Self? {
        guard let directory, directory.isFileURL else { return nil }
        let file = directory.appendingPathComponent(filename, isDirectory: false)
        do {
            let handle = try FileHandle(forReadingFrom: file)
            defer { try? handle.close() }
            // Bound the read itself, including a file replaced/grown after opening.
            let data = try handle.read(upToCount: maximumBytes + 1) ?? Data()
            guard !data.isEmpty, data.count <= maximumBytes,
                  let value = try? JSONDecoder().decode(Self.self, from: data),
                  value.isValid(now: now) else { return nil }
            return value
        } catch {
            return nil
        }
    }
}
