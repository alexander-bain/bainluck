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
/// Shows live probability (with optional verified live score), scheduled pregame probability
/// (without fake 0–0), and final result (without stale pre-final probability).
/// Games without odds (and not final) are omitted so the slot falls back to the launcher.
nonisolated struct WatchRectangularReading: Codable, Sendable, Equatable {
    enum Kind: String, Codable, Sendable {
        case liveForecast
        case scheduledForecast
        case finalResult
        case futureForecast
    }

    static let maxSingleLineHeaderCharacters = 26
    static let maxSingleLineMetadataCharacters = 28
    static let liveAgeThresholdSeconds: TimeInterval = 120

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
    let subOnePercent: Bool?
    let aboveNinetyNinePercent: Bool?

    init(
        version: Int,
        eventID: Int,
        kind: Kind,
        homeName: String,
        awayName: String,
        home: WatchCompactTeamIdentity?,
        away: WatchCompactTeamIdentity?,
        homePercent: Int?,
        homeScore: Int?,
        awayScore: Int?,
        commenceTime: Date?,
        stateLabel: String,
        observedAt: Date,
        scoreObservedAt: Date?,
        subOnePercent: Bool? = nil,
        aboveNinetyNinePercent: Bool? = nil
    ) {
        self.version = version
        self.eventID = eventID
        self.kind = kind
        self.homeName = homeName
        self.awayName = awayName
        self.home = home
        self.away = away
        self.homePercent = homePercent
        self.homeScore = homeScore
        self.awayScore = awayScore
        self.commenceTime = commenceTime
        self.stateLabel = stateLabel
        self.observedAt = observedAt
        self.scoreObservedAt = scoreObservedAt
        self.subOnePercent = subOnePercent
        self.aboveNinetyNinePercent = aboveNinetyNinePercent
    }

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
                      abs(sClock.timeIntervalSince(observedAt)) <= Self.liveAgeThresholdSeconds else { return false }
            }
            let probability = (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
            return snapshot.title == "\(homeName) win" && snapshot.detail == "\(probability) · Live"
        case .scheduledForecast:
            guard ["Scheduled", "Upcoming", "Pregame"].contains(stateLabel),
                  let homePercent, (0...100).contains(homePercent),
                  homeScore == nil, awayScore == nil, scoreObservedAt == nil else { return false }
            if let start = commenceTime, !start.timeIntervalSinceReferenceDate.isFinite { return false }
            let probability = (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
            return snapshot.title == "\(homeName) win" && snapshot.detail == "\(probability) · \(stateLabel)"
        case .finalResult:
            guard stateLabel == "Final",
                  homePercent == nil,
                  commenceTime == nil,
                  let hs = homeScore, let ascore = awayScore, hs >= 0, ascore >= 0,
                  scoreObservedAt == observedAt else { return false }
            if hs > ascore { return snapshot.title == "\(homeName) won" && snapshot.detail == "Final · \(hs)–\(ascore)" }
            if ascore > hs { return snapshot.title == "\(awayName) won" && snapshot.detail == "Final · \(ascore)–\(hs)" }
            return snapshot.title == "\(awayName) at \(homeName)" && snapshot.detail == "Final · tied \(hs)–\(ascore)"
        case .futureForecast:
            guard stateLabel == "Market",
                  let homePercent, (1...99).contains(homePercent),
                  home == nil, away == nil,
                  homeScore == nil, awayScore == nil,
                  commenceTime == nil, scoreObservedAt == nil,
                  !(subOnePercent == true && aboveNinetyNinePercent == true) else { return false }
            guard let pct = formattedHomePercent else { return false }
            return snapshot.title == homeName && snapshot.detail == "\(awayName) \(pct)"
        }
    }

    var formattedHomePercent: String? {
        if subOnePercent == true { return "<1%" }
        if aboveNinetyNinePercent == true { return ">99%" }
        guard let homePercent, (0...100).contains(homePercent) else { return nil }
        return (Double(homePercent) / 100).formatted(.percent.precision(.fractionLength(0)))
    }

    /// Matchup or market header line (Line 1), appending verified live score when present on a live probability reading.
    func headerLine(preferCompact: Bool = false) -> String {
        if kind == .futureForecast {
            return homeName
        }
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

    /// Primary reading line (Line 2): compact side probability ("SF 64%"), market outcome ("Newsom 23%"), or final result ("Final · SF 4, LA 2").
    func primaryLine(preferCompact: Bool = false, at now: Date) -> String {
        switch kind {
        case .liveForecast, .scheduledForecast:
            guard let pct = formattedHomePercent else { return "Win probability unavailable" }
            let team = home?.abbreviation ?? homeName
            return "\(team) \(pct)"
        case .futureForecast:
            guard let pct = formattedHomePercent else { return "Probability unavailable" }
            return "\(awayName) \(pct)"
        case .finalResult:
            guard let hs = homeScore, let ascore = awayScore else { return "Final score unavailable" }
            let homeLabel = home?.abbreviation ?? homeName
            let awayLabel = away?.abbreviation ?? awayName
            if hs > ascore {
                return "Final · \(homeLabel) \(hs), \(awayLabel) \(ascore)"
            }
            return "Final · \(awayLabel) \(ascore), \(homeLabel) \(hs)"
        }
    }

    func isAgedLive(at now: Date) -> Bool {
        guard kind == .liveForecast else { return false }
        let elapsed = now.timeIntervalSince(observedAt)
        return elapsed.isFinite && elapsed > Self.liveAgeThresholdSeconds
    }

    func isAgedFuture(at now: Date) -> Bool {
        guard kind == .futureForecast else { return false }
        let elapsed = now.timeIntervalSince(observedAt)
        return elapsed.isFinite && elapsed > Self.liveAgeThresholdSeconds
    }

    static func asOfClock(_ date: Date, timeZone: TimeZone = .current) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }

    /// Upcoming game start slot wording (#12640): "Today 7:15 PM" same day, "Sun 1:25 PM" within 6 days,
    /// or "Nov 23, 5:15 PM" further out.
    static func upcomingStartClock(_ start: Date, now: Date, timeZone: TimeZone = .current) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        if calendar.isDate(start, inSameDayAs: now) {
            return "Today \(asOfClock(start, timeZone: timeZone))"
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        let delta = start.timeIntervalSince(now)
        formatter.dateFormat = delta < 6 * 24 * 3600 ? "EEE h:mm a" : "MMM d, h:mm a"
        return formatter.string(from: start)
    }

    /// Status and observation age line (Line 3). Never uses "Saved", "Stale", or "Checked".
    func metadataLine(at now: Date, timeZone: TimeZone = .current) -> String {
        if kind == .scheduledForecast, let start = commenceTime {
            if now >= start {
                return "Open to update"
            }
            return Self.upcomingStartClock(start, now: now, timeZone: timeZone)
        }
        if isAgedLive(at: now) || isAgedFuture(at: now) {
            return "As of \(Self.asOfClock(observedAt, timeZone: timeZone))"
        }
        let age = Self.compactAge(observedAt: observedAt, now: now) ?? "no time"
        if kind == .finalResult || kind == .futureForecast {
            return age
        }
        return "\(stateLabel) · \(age)"
    }

    func accessibilityDescription(at now: Date, timeZone: TimeZone = .current) -> String {
        switch kind {
        case .liveForecast:
            let scorePart: String = {
                guard let ascore = awayScore, let hs = homeScore else { return "" }
                return " Score \(awayName) \(ascore), \(homeName) \(hs)."
            }()
            let pct = formattedHomePercent ?? "unavailable"
            if isAgedLive(at: now) {
                let clockText = Self.asOfClock(observedAt, timeZone: timeZone)
                return "\(awayName) at \(homeName).\(scorePart) \(homeName) \(pct). As of \(clockText). Open your game in Bain Luck."
            }
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "time unavailable"
            return "\(awayName) at \(homeName).\(scorePart) \(homeName) \(pct). Live, \(age). Open your game in Bain Luck."
        case .scheduledForecast:
            let pct = formattedHomePercent ?? "unavailable"
            if let start = commenceTime {
                if now >= start {
                    return "\(awayName) at \(homeName). \(homeName) \(pct). Open to update. Open your game in Bain Luck."
                }
                let startText = Self.upcomingStartClock(start, now: now, timeZone: timeZone)
                return "\(awayName) at \(homeName). \(homeName) \(pct). \(startText). Open your game in Bain Luck."
            }
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "time unavailable"
            return "\(awayName) at \(homeName). \(homeName) \(pct). \(stateLabel), \(age). Open your game in Bain Luck."
        case .futureForecast:
            let pct = formattedHomePercent ?? "unavailable"
            if isAgedFuture(at: now) {
                let clockText = Self.asOfClock(observedAt, timeZone: timeZone)
                return "\(homeName). \(awayName) \(pct). As of \(clockText). Open in Bain Luck."
            }
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "time unavailable"
            return "\(homeName). \(awayName) \(pct). \(age). Open in Bain Luck."
        case .finalResult:
            let hs = homeScore ?? 0
            let ascore = awayScore ?? 0
            let age = Self.spokenAge(observedAt: observedAt, now: now) ?? "time unavailable"
            if hs > ascore {
                return "\(awayName) at \(homeName). Final, \(homeName) \(hs), \(awayName) \(ascore). \(age). Open your game in Bain Luck."
            }
            return "\(awayName) at \(homeName). Final, \(awayName) \(ascore), \(homeName) \(hs). \(age). Open your game in Bain Luck."
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
        let ageSwitch = reading.observedAt.addingTimeInterval(liveAgeThresholdSeconds + 1)
        if (reading.kind == .liveForecast || reading.kind == .futureForecast), ageSwitch > now {
            dates.append(ageSwitch)
        }
        let horizon = now.addingTimeInterval(7 * 24 * 3600)
        if let start = reading.commenceTime,
           reading.kind == .scheduledForecast,
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
