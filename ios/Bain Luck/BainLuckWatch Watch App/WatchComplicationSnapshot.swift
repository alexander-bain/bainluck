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
    let rectangularReading: WatchRectangularReading?

    init(version: Int = 1, eventID: Int, title: String, detail: String,
         observedAt: Date, savedAt: Date, circularReading: WatchCircularReading? = nil,
         rectangularReading: WatchRectangularReading? = nil) {
        self.version = version
        self.eventID = eventID
        self.title = title
        self.detail = detail
        self.observedAt = observedAt
        self.savedAt = savedAt
        self.circularReading = circularReading
        self.rectangularReading = rectangularReading
    }

    private enum CodingKeys: String, CodingKey {
        case version, eventID, title, detail, observedAt, savedAt, circularReading, rectangularReading
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
        rectangularReading = try? c.decode(WatchRectangularReading.self, forKey: .rectangularReading)
    }

    var validatedCircularReading: WatchCircularReading? {
        return validatedCircularReading(now: Date())
    }

    func validatedCircularReading(now: Date) -> WatchCircularReading? {
        guard isValid(now: now), let circularReading, circularReading.matches(self) else { return nil }
        return circularReading
    }

    var validatedRectangularReading: WatchRectangularReading? {
        return validatedRectangularReading(now: Date())
    }

    func validatedRectangularReading(now: Date) -> WatchRectangularReading? {
        guard isValid(now: now), let rectangularReading, rectangularReading.matches(self) else { return nil }
        return rectangularReading
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

/// Structured large-rectangular (`accessoryRectangular`) reading for #4933.
/// Supports live probability (with optional verified live score), live score-only,
/// scheduled pregame probability or scheduled start (without fake 0–0), final result
/// (without stale pre-final probability), and explicit saved/stale observation age.
nonisolated struct WatchRectangularReading: Codable, Sendable, Equatable {
    enum Kind: String, Codable, Sendable {
        case liveForecast
        case liveScoreOnly
        case scheduledForecast
        case scheduledStart
        case finalResult
    }

    static let maxSingleLineHeaderCharacters = 26
    static let maxCompactScheduledPrimaryCharacters = 24
    static let maxSingleLineMetadataCharacters = 28
    static let liveStaleThresholdSeconds: TimeInterval = 120

    let version: Int
    let eventID: Int
    let kind: Kind
    let homeName: String
    let awayName: String
    let home: WatchCompactTeamIdentity?
    let away: WatchCompactTeamIdentity?
    let homePercent: Int?
    let homeScore: Int?
    let awayScore: Int?
    let commenceTime: Date?
    let stateLabel: String
    let observedAt: Date
    let scoreObservedAt: Date?

    func matches(_ snapshot: WatchComplicationSnapshot) -> Bool {
        guard snapshot.isValid(now: snapshot.savedAt),
              version == 1,
              eventID == snapshot.eventID,
              observedAt == snapshot.observedAt,
              !homeName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !awayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        if let home, !home.isValid { return false }
        if let away, !away.isValid { return false }
        if let home, let away, (home.teamID == away.teamID || home.abbreviation == away.abbreviation) {
            return false
        }
        switch kind {
        case .liveForecast:
            guard stateLabel == "Live",
                  let homePercent, (0...100).contains(homePercent),
                  commenceTime == nil else { return false }
            if homeScore != nil || awayScore != nil || scoreObservedAt != nil {
                guard let hs = homeScore, let ascore = awayScore, hs >= 0, ascore >= 0,
                      let sClock = scoreObservedAt,
                      sClock.timeIntervalSinceReferenceDate.isFinite,
                      sClock <= snapshot.savedAt,
                      abs(sClock.timeIntervalSince(observedAt)) <= Self.liveStaleThresholdSeconds else { return false }
            }
            let probability = (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
            return snapshot.title == "\(homeName) win" && snapshot.detail == "\(probability) · Live"
        case .liveScoreOnly:
            guard stateLabel == "Live",
                  homePercent == nil,
                  commenceTime == nil,
                  let hs = homeScore, let ascore = awayScore, hs >= 0, ascore >= 0,
                  scoreObservedAt == observedAt else { return false }
            return snapshot.title == "\(awayName) at \(homeName)"
                && snapshot.detail == "Score \(ascore)–\(hs) · Live"
        case .scheduledForecast:
            guard ["Scheduled", "Upcoming", "Pregame"].contains(stateLabel),
                  let homePercent, (0...100).contains(homePercent),
                  homeScore == nil, awayScore == nil, scoreObservedAt == nil else { return false }
            if let start = commenceTime, !start.timeIntervalSinceReferenceDate.isFinite { return false }
            let probability = (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
            return snapshot.title == "\(homeName) win" && snapshot.detail == "\(probability) · \(stateLabel)"
        case .scheduledStart:
            guard ["Scheduled", "Upcoming", "Pregame"].contains(stateLabel),
                  homePercent == nil,
                  homeScore == nil, awayScore == nil, scoreObservedAt == nil,
                  let start = commenceTime, start.timeIntervalSinceReferenceDate.isFinite else { return false }
            return snapshot.title == "\(awayName) at \(homeName)"
                && snapshot.detail.hasPrefix("\(stateLabel) · ")
        case .finalResult:
            guard stateLabel == "Final",
                  homePercent == nil,
                  commenceTime == nil,
                  let hs = homeScore, let ascore = awayScore, hs >= 0, ascore >= 0,
                  scoreObservedAt == observedAt else { return false }
            if hs > ascore { return snapshot.title == "\(homeName) won" && snapshot.detail == "Final · \(hs)–\(ascore)" }
            if ascore > hs { return snapshot.title == "\(awayName) won" && snapshot.detail == "Final · \(ascore)–\(hs)" }
            return snapshot.title == "\(awayName) at \(homeName)" && snapshot.detail == "Final · tied \(hs)–\(ascore)"
        }
    }

    var formattedHomePercent: String? {
        guard let homePercent, (0...100).contains(homePercent) else { return nil }
        return (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
    }

    /// Matchup header line (Line 1), appending verified live score when present on a live probability reading.
    func headerLine(preferCompact: Bool = false) -> String {
        let fullMatchup = "\(awayName) at \(homeName)"
        let compactMatchup: String? = {
            guard let away, let home, away.isValid, home.isValid else { return nil }
            return "\(away.abbreviation) at \(home.abbreviation)"
        }()
        let scoreSuffix: String = {
            guard kind == .liveForecast, let ascore = awayScore, let hs = homeScore else { return "" }
            return " · \(ascore)–\(hs)"
        }()
        if preferCompact, let compactMatchup {
            return compactMatchup + scoreSuffix
        }
        let fullCandidate = fullMatchup + scoreSuffix
        if fullCandidate.count > Self.maxSingleLineHeaderCharacters, let compactMatchup {
            return compactMatchup + scoreSuffix
        }
        return fullCandidate
    }

    /// Primary reading line (Line 2): named probability, live score with honest missing-probability copy,
    /// scheduled start time, or final winner + score.
    func primaryLine(preferCompact: Bool = false, at now: Date) -> String {
        switch kind {
        case .liveForecast, .scheduledForecast:
            guard let pct = formattedHomePercent else { return "Win probability unavailable" }
            let team = (preferCompact ? home?.abbreviation : nil) ?? homeName
            return "\(team) win \(pct)"
        case .liveScoreOnly:
            guard let ascore = awayScore, let hs = homeScore else { return "Score unavailable" }
            // The compact card drops "Score": the matchup line above already names the sides,
            // and a 41 mm face cut "Score 112–108 · No win prob" to "No win pr…" (lane1b A7).
            return preferCompact ? "\(ascore)–\(hs) · No win prob" : "Score \(ascore)–\(hs) · No win prob"
        case .scheduledStart:
            guard let start = commenceTime else {
                return preferCompact ? "Time unavailable" : "\(stateLabel) · time unavailable"
            }
            if now >= start {
                return preferCompact ? "Past start · check app" : "Start time passed · check app"
            }
            let formattedStart = start.formatted(.dateTime.month(.abbreviated).day().hour().minute())
            return preferCompact ? "Start \(formattedStart)" : "\(stateLabel) · \(formattedStart)"
        case .finalResult:
            guard let hs = homeScore, let ascore = awayScore else { return "Final score unavailable" }
            if hs > ascore {
                let winner = (preferCompact ? home?.abbreviation : nil) ?? homeName
                return "\(winner) won · \(hs)–\(ascore)"
            }
            if ascore > hs {
                let winner = (preferCompact ? away?.abbreviation : nil) ?? awayName
                return "\(winner) won · \(ascore)–\(hs)"
            }
            return "Final · tied \(hs)–\(ascore)"
        }
    }

    func isStale(at now: Date) -> Bool {
        guard kind == .liveForecast || kind == .liveScoreOnly else { return false }
        let elapsed = now.timeIntervalSince(observedAt)
        return elapsed.isFinite && elapsed > Self.liveStaleThresholdSeconds
    }

    /// Status and compact observation age line (Line 3). Never presents a saved reading as live now,
    /// and stays within `maxSingleLineMetadataCharacters` so narrow Watch faces keep age/stale/past-start cues.
    func metadataLine(at now: Date) -> String {
        if kind == .scheduledStart {
            if let start = commenceTime, now >= start {
                let age = Self.compactAge(observedAt: observedAt, now: now) ?? "no time"
                return "Saved · Past start · \(age)"
            }
            return "Saved · No win prob"
        }
        let age = Self.compactAge(observedAt: observedAt, now: now) ?? "no time"
        if kind == .scheduledForecast, let start = commenceTime, now >= start {
            return "Saved · Past start · \(age)"
        }
        if isStale(at: now) {
            return "Saved · Stale · \(age)"
        }
        return "Saved · \(stateLabel) · \(age)"
    }

    func accessibilityDescription(at now: Date) -> String {
        let staleNote = isStale(at: now) ? " Stale reading." : ""
        switch kind {
        case .liveForecast:
            let scorePart: String = {
                guard let ascore = awayScore, let hs = homeScore else { return "" }
                return " Score \(awayName) \(ascore), \(homeName) \(hs)."
            }()
            let pct = formattedHomePercent ?? "unavailable"
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "observation time unavailable"
            return "Saved reading. \(awayName) at \(homeName).\(scorePart) \(homeName) win probability \(pct). Live. Observed \(age).\(staleNote) Open your game in Bain Luck."
        case .liveScoreOnly:
            let ascore = awayScore ?? 0
            let hs = homeScore ?? 0
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "observation time unavailable"
            return "Saved reading. \(awayName), score \(ascore). \(homeName), score \(hs). Win probability unavailable. Live. Observed \(age).\(staleNote) Open your game in Bain Luck."
        case .scheduledForecast:
            let pct = formattedHomePercent ?? "unavailable"
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "observation time unavailable"
            if let start = commenceTime, now >= start {
                return "Saved reading. \(awayName) at \(homeName). \(homeName) win probability \(pct). Scheduled start has passed; game status unconfirmed. Observed \(age). Open your game in Bain Luck."
            }
            return "Saved reading. \(awayName) at \(homeName). \(homeName) win probability \(pct). \(stateLabel). Observed \(age). Open your game in Bain Luck."
        case .scheduledStart:
            let startText = commenceTime.map { $0.formatted(.dateTime.month(.abbreviated).day().hour().minute()) } ?? "time unavailable"
            if let start = commenceTime, now >= start {
                let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "time unavailable"
                return "Saved reading. \(awayName) at \(homeName). Scheduled start \(startText) has passed; game status unconfirmed. Win probability unavailable. Saved \(age). Open your game in Bain Luck."
            }
            return "Saved reading. \(awayName) at \(homeName). \(stateLabel) \(startText). Win probability unavailable. Open your game in Bain Luck."
        case .finalResult:
            let hs = homeScore ?? 0
            let ascore = awayScore ?? 0
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "observation time unavailable"
            if hs > ascore {
                return "Saved reading. \(awayName), score \(ascore). \(homeName) won, score \(hs). Final. Observed \(age). Open your game in Bain Luck."
            }
            if ascore > hs {
                return "Saved reading. \(awayName) won, score \(ascore). \(homeName), score \(hs). Final. Observed \(age). Open your game in Bain Luck."
            }
            return "Saved reading. \(awayName), score \(ascore). \(homeName), score \(hs). Final tie. Observed \(age). Open your game in Bain Luck."
        }
    }

    static func compactAge(observedAt: Date, now: Date) -> String? {
        let raw = now.timeIntervalSince(observedAt)
        guard raw.isFinite, raw >= 0 else { return nil }
        let seconds = Int(raw)
        if seconds < 60 { return "<1m ago" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes)m ago" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours)h ago" }
        return "\(hours / 24)d ago"
    }

    static func spokenAge(observedAt: Date, now: Date) -> String? {
        let raw = now.timeIntervalSince(observedAt)
        guard raw.isFinite, raw >= 0 else { return nil }
        let seconds = Int(raw)
        if seconds < 60 { return "less than 1 minute ago" }
        let minutes = seconds / 60
        if minutes < 60 { return minutes == 1 ? "1 minute ago" : "\(minutes) minutes ago" }
        let hours = minutes / 60
        if hours < 24 { return hours == 1 ? "1 hour ago" : "\(hours) hours ago" }
        let days = hours / 24
        return days == 1 ? "1 day ago" : "\(days) days ago"
    }

    /// WidgetKit renders each entry at its fixed date. Plan the actual text transitions
    /// without pretending that an unchanged producer reading triggers a reload.
    static func timelineDates(for snapshot: WatchComplicationSnapshot?, now: Date) -> [Date] {
        guard now.timeIntervalSinceReferenceDate.isFinite,
              let snapshot, let reading = snapshot.validatedRectangularReading(now: now) else { return [now] }
        var dates = [now]
        let stale = reading.observedAt.addingTimeInterval(liveStaleThresholdSeconds + 1)
        if (reading.kind == .liveForecast || reading.kind == .liveScoreOnly), stale > now {
            dates.append(stale)
        }
        let horizon = now.addingTimeInterval(7 * 24 * 3600)
        if let start = reading.commenceTime,
           (reading.kind == .scheduledStart || reading.kind == .scheduledForecast),
           start > now, start <= horizon { dates.append(start) }
        // Age changes every minute up to one hour, hourly to one day, then daily.
        // Keep the list finite; WidgetKit requests the next timeline at its end.
        var elapsed = max(0, now.timeIntervalSince(reading.observedAt))
        for _ in 0..<128 {
            let nextElapsed: TimeInterval
            if elapsed < 3600 {
                nextElapsed = (floor(elapsed / 60) + 1) * 60
            } else if elapsed < 24 * 3600 {
                nextElapsed = (floor(elapsed / 3600) + 1) * 3600
            } else {
                nextElapsed = (floor(elapsed / 86400) + 1) * 86400
            }
            let boundary = reading.observedAt.addingTimeInterval(nextElapsed)
            guard boundary > now, boundary <= horizon else { break }
            dates.append(boundary)
            elapsed = nextElapsed
        }
        return Array(Set(dates)).sorted()
    }
}
