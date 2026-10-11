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
    let circularReading: WatchCircularReading?

    init(version: Int = 1, eventID: Int, title: String, detail: String,
         observedAt: Date, savedAt: Date, circularReading: WatchCircularReading? = nil) {
        self.version = version
        self.eventID = eventID
        self.title = title
        self.detail = detail
        self.observedAt = observedAt
        self.savedAt = savedAt
        self.circularReading = circularReading
    }

    private enum CodingKeys: String, CodingKey {
        case version, eventID, title, detail, observedAt, savedAt, circularReading
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(Int.self, forKey: .version)
        eventID = try c.decode(Int.self, forKey: .eventID)
        title = try c.decode(String.self, forKey: .title)
        detail = try c.decode(String.self, forKey: .detail)
        observedAt = try c.decode(Date.self, forKey: .observedAt)
        savedAt = try c.decode(Date.self, forKey: .savedAt)
        // Unknown or malformed optional compact data cannot hide the rectangular reading.
        circularReading = try? c.decode(WatchCircularReading.self, forKey: .circularReading)
    }

    var validatedCircularReading: WatchCircularReading? {
        return validatedCircularReading(now: Date())
    }

    func validatedCircularReading(now: Date) -> WatchCircularReading? {
        guard isValid(now: now), let circularReading, circularReading.matches(self) else { return nil }
        return circularReading
    }

    /// Corner's curved label is deliberately bounded; other families keep their contract.
    func validatedCornerForecast(showsWidgetLabel: Bool, now: Date = Date()) -> WatchCircularReading? {
        guard showsWidgetLabel, let reading = validatedCircularReading(now: now),
              reading.kind == .forecast, let home = reading.home,
              (1...2).contains(home.abbreviation.count) else { return nil }
        return reading
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

/// The public API's canonical side identity, not a client-generated name abbreviation.
nonisolated struct WatchCompactTeamIdentity: Codable, Sendable, Equatable {
    let teamID: Int
    let abbreviation: String
    private enum CodingKeys: String, CodingKey { case teamID = "team_id", abbreviation }
    var isValid: Bool {
        teamID > 0 && (1...4).contains(abbreviation.count)
            && abbreviation.unicodeScalars.allSatisfy { (65...90).contains($0.value) || (48...57).contains($0.value) }
    }
}

/// Optional v1 extension: old saved readings remain valid and launch honestly.
nonisolated struct WatchCircularReading: Codable, Sendable, Equatable {
    enum Kind: String, Codable, Sendable { case forecast, score, final }
    let version: Int
    let eventID: Int
    let kind: Kind
    let homeName: String
    let awayName: String
    let home: WatchCompactTeamIdentity?
    let away: WatchCompactTeamIdentity?
    let percent: Int?
    let homeScore: Int?
    let awayScore: Int?
    let stateLabel: String
    let observedAt: Date

    func matches(_ snapshot: WatchComplicationSnapshot) -> Bool {
        guard snapshot.isValid(now: snapshot.savedAt), version == 1, eventID == snapshot.eventID, observedAt == snapshot.observedAt,
              !homeName.isEmpty, !awayName.isEmpty else { return false }
        switch kind {
        case .forecast:
            guard home?.isValid == true, let percent, (0...100).contains(percent),
                  homeScore == nil, awayScore == nil,
                  ["Live", "Scheduled", "Upcoming", "Pregame"].contains(stateLabel) else { return false }
            if let away, away.teamID == home?.teamID || away.abbreviation == home?.abbreviation { return false }
            let probability = (Double(percent) / 100).formatted(.percent.precision(.fractionLength(0)))
            return snapshot.title == "\(homeName) win" && snapshot.detail == "\(probability) · \(stateLabel)"
        case .score, .final:
            guard home?.isValid == true, away?.isValid == true,
                  home?.teamID != away?.teamID, home?.abbreviation != away?.abbreviation,
                  percent == nil, let homeScore, let awayScore, homeScore >= 0, awayScore >= 0 else { return false }
            if kind == .score {
                return stateLabel == "Live" && snapshot.title == "\(awayName) at \(homeName)"
                    && snapshot.detail == "Score \(awayScore)–\(homeScore) · Live"
            }
            guard stateLabel == "Final" else { return false }
            if homeScore > awayScore { return snapshot.title == "\(homeName) won" && snapshot.detail == "Final · \(homeScore)–\(awayScore)" }
            if awayScore > homeScore { return snapshot.title == "\(awayName) won" && snapshot.detail == "Final · \(awayScore)–\(homeScore)" }
            return snapshot.title == "\(awayName) at \(homeName)" && snapshot.detail == "Final · tied \(homeScore)–\(awayScore)"
        }
    }

    var subject: String {
        switch kind {
        case .forecast:
            guard let home, home.isValid else { return "" }
            return "\(home.abbreviation) win"
        case .score:
            guard let home, let away, home.isValid, away.isValid else { return "" }
            return "\(away.abbreviation)·\(home.abbreviation)"
        case .final:
            guard let home, let away, home.isValid, away.isValid,
                  let homeScore, let awayScore else { return "" }
            if homeScore > awayScore { return "\(home.abbreviation) won" }
            if awayScore > homeScore { return "\(away.abbreviation) won" }
            return "\(away.abbreviation)·\(home.abbreviation)"
        }
    }
    var value: String {
        switch kind {
        case .forecast:
            guard let percent, (0...100).contains(percent) else { return "" }
            return (Double(percent) / 100).formatted(.percent.precision(.fractionLength(0)))
        case .score:
            guard let homeScore, let awayScore else { return "" }
            return "Score \(awayScore)–\(homeScore)"
        case .final:
            guard let homeScore, let awayScore else { return "" }
            // The named winner + Final earns the small slot. Full score is spoken/on tap.
            return homeScore == awayScore ? "Final tie" : "Final"
        }
    }
}
