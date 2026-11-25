import Foundation
#if canImport(WidgetKit)
import WidgetKit
#endif

/// Project using the same rounded probability as the app; never export raw auth/API data.
nonisolated enum WatchComplicationProjection {
    static let defaultGameClockSkewTolerance: TimeInterval = 15

    static func snapshot(
        game: WatchSelectedGame,
        savedAt: Date,
        clockSkewTolerance: TimeInterval = 0
    ) -> WatchComplicationSnapshot? {
        let title: String
        let detail: String
        let observed: Date?
        let kind: WatchCircularReading.Kind
        var rectangularKind: WatchRectangularReading.Kind?
        var rectHomeScore: Int?
        var rectAwayScore: Int?
        var rectScoreObserved: Date?
        var rectCommenceTime: Date?
        if game.isFinal {
            kind = .final
            rectangularKind = .finalResult
            guard let home = game.homeScore, let away = game.awayScore, home >= 0, away >= 0 else { return nil }
            if home > away { title = "\(game.homeTeam) won"; detail = "Final · \(home)–\(away)" }
            else if away > home { title = "\(game.awayTeam) won"; detail = "Final · \(away)–\(home)" }
            else { title = "\(game.awayTeam) at \(game.homeTeam)"; detail = "Final · tied \(home)–\(away)" }
            observed = clampedObservation(game.scoreObservedAt, savedAt: savedAt, tolerance: clockSkewTolerance)
            rectHomeScore = home
            rectAwayScore = away
            rectScoreObserved = observed
        } else {
            let statusLower = game.status?.lowercased() ?? ""
            guard ["live", "scheduled", "upcoming", "in_progress", "pregame"].contains(statusLower),
                  game.showsForecast else { return nil }
            if let probability = game.homeProbabilityText,
               let clock = clampedObservation(game.probabilityObservedAt, savedAt: savedAt, tolerance: clockSkewTolerance) {
                kind = .forecast
                title = "\(game.homeTeam) win"
                detail = "\(probability) · \(game.stateLabel)"
                observed = clock
                if ["live", "in_progress"].contains(statusLower) {
                    rectangularKind = .liveForecast
                    if let hs = game.homeScore, let ascore = game.awayScore, hs >= 0, ascore >= 0,
                       let sClock = clampedObservation(game.scoreObservedAt, savedAt: savedAt, tolerance: clockSkewTolerance),
                       abs(sClock.timeIntervalSince(clock)) <= WatchRectangularReading.liveAgeThresholdSeconds {
                        rectHomeScore = hs
                        rectAwayScore = ascore
                        rectScoreObserved = sClock
                    }
                } else {
                    rectangularKind = .scheduledForecast
                    if let start = game.commenceTime, start.timeIntervalSinceReferenceDate.isFinite {
                        rectCommenceTime = start
                    }
                }
            } else if ["live", "in_progress"].contains(statusLower), let home = game.homeScore, let away = game.awayScore,
                      home >= 0, away >= 0,
                      let clock = clampedObservation(game.scoreObservedAt, savedAt: savedAt, tolerance: clockSkewTolerance) {
                // Keep parent/circular score snapshot intact; rectangular face omits score-without-odds.
                kind = .score
                title = "\(game.awayTeam) at \(game.homeTeam)"
                detail = "Score \(away)–\(home) · Live"
                observed = clock
            } else {
                return nil
            }
        }
        guard let observed, validObservation(observed, savedAt: savedAt) else { return nil }
        let compact = WatchCircularReading(version: 1, eventID: game.id, kind: kind,
            homeName: game.homeTeam, awayName: game.awayTeam,
            home: game.homeCompactIdentity, away: game.awayCompactIdentity,
            percent: kind == .forecast ? game.homeRenderedPercent : nil,
            homeScore: kind == .forecast ? nil : game.homeScore,
            awayScore: kind == .forecast ? nil : game.awayScore,
            stateLabel: kind == .final ? "Final" : game.stateLabel, observedAt: observed)
        let validHome: WatchCompactTeamIdentity? = game.homeCompactIdentity.flatMap { $0.isValid ? $0 : nil }
        let validAway: WatchCompactTeamIdentity? = game.awayCompactIdentity.flatMap {
            guard $0.isValid else { return nil }
            if let vh = validHome, (vh.teamID == $0.teamID || vh.abbreviation == $0.abbreviation) { return nil }
            return $0
        }
        let rectangular: WatchRectangularReading? = rectangularKind.map { rKind in
            WatchRectangularReading(
                version: 1,
                eventID: game.id,
                kind: rKind,
                homeName: game.homeTeam,
                awayName: game.awayTeam,
                home: validHome,
                away: validAway,
                homePercent: (rKind == .liveForecast || rKind == .scheduledForecast) ? game.homeRenderedPercent : nil,
                homeScore: rectHomeScore,
                awayScore: rectAwayScore,
                commenceTime: rectCommenceTime,
                stateLabel: kind == .final ? "Final" : game.stateLabel,
                observedAt: observed,
                scoreObservedAt: rectScoreObserved
            )
        }
        let parent = WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt)
        let checkedRectangular = rectangular.flatMap { $0.matches(parent) ? $0 : nil }
        return WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt,
            circularReading: compact.matches(parent) ? compact : nil,
            rectangularReading: checkedRectangular,
            matchup: checkedRectangular == nil ? nil : matchupFacts(game))
    }

    /// Direction 217: what the Matchup look needs beyond the rectangular reading.
    static func matchupFacts(_ game: WatchSelectedGame) -> WatchMatchupFacts217 {
        let pregame = game.pregameRenderedPercents
        let drawSport = game.sportKey.map { DrawPricedWinner.sportPricesADraw($0) } ?? false
        let isThreeWay = drawSport || game.drawProbability != nil || game.prematchDrawProbability != nil
        let threeWayCurrent: (draw: Int?, away: Int?) = {
            guard game.drawProbability != nil else { return (nil, nil) }
            if let h = game.homeProbability, let d = game.drawProbability, let a = game.awayProbability,
               h.isFinite, d.isFinite, a.isFinite {
                let percents = renderedCardPercents([h, d, a])
                return (
                    percents.count > 1 ? percents[1] : renderedPercent(d),
                    percents.count > 2 ? percents[2] : renderedPercent(a)
                )
            }
            return (renderedPercent(game.drawProbability), renderedPercent(game.awayProbability))
        }()
        let pregameDraw = renderedPercent(game.prematchDrawProbability)
        return WatchMatchupFacts217(
            homePrimary: game.homePrimaryColor, homeSecondary: game.homeSecondaryColor,
            awayPrimary: game.awayPrimaryColor, awaySecondary: game.awaySecondaryColor,
            homeLogo: game.homeLogoURL, awayLogo: game.awayLogoURL,
            pregameHomePercent: pregame.home, pregameAwayPercent: pregame.away,
            clock: game.isLive ? game.liveClockText : nil,
            drawPercent: threeWayCurrent.draw,
            awayPercent: threeWayCurrent.away,
            pregameDrawPercent: pregameDraw,
            isThreeWay: isThreeWay ? true : nil
        )
    }

    /// #12640 — projects a pinned market outcome onto the rectangular Watch face slot ("Newsom 23%").
    /// Markets without a valid open probability in (0, 1) are rejected so nothing without a chance shows.
    static func futureSnapshot(
        marketID: Int,
        marketTitle: String,
        outcomeName: String,
        probability: Double,
        observedAt: Date,
        savedAt: Date
    ) -> WatchComplicationSnapshot? {
        let trimmedMarket = marketTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedOutcome = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard marketID > 0,
              !trimmedMarket.isEmpty,
              !trimmedOutcome.isEmpty,
              probability.isFinite,
              probability > 0,
              probability < 1,
              validObservation(observedAt, savedAt: savedAt) else {
            return nil
        }
        let subOne = probability < 0.005
        let aboveNinetyNine = probability > 0.995
        let clampedPercent: Int = {
            if subOne { return 1 }
            if aboveNinetyNine { return 99 }
            return min(99, max(1, Int((probability * 100).rounded())))
        }()
        let reading = WatchRectangularReading(
            version: 1,
            eventID: marketID,
            kind: .futureForecast,
            homeName: trimmedMarket,
            awayName: trimmedOutcome,
            home: nil,
            away: nil,
            homePercent: clampedPercent,
            homeScore: nil,
            awayScore: nil,
            commenceTime: nil,
            stateLabel: "Market",
            observedAt: observedAt,
            scoreObservedAt: nil,
            subOnePercent: subOne ? true : nil,
            aboveNinetyNinePercent: aboveNinetyNine ? true : nil
        )
        guard let pct = reading.formattedHomePercent else { return nil }
        let detail = "\(trimmedOutcome) \(pct)"
        let parent = WatchComplicationSnapshot(
            version: 1,
            eventID: marketID,
            title: trimmedMarket,
            detail: detail,
            observedAt: observedAt,
            savedAt: savedAt
        )
        guard reading.matches(parent) else { return nil }
        return WatchComplicationSnapshot(
            version: 1,
            eventID: marketID,
            title: trimmedMarket,
            detail: detail,
            observedAt: observedAt,
            savedAt: savedAt,
            circularReading: nil,
            rectangularReading: reading
        )
    }

    private static func clampedObservation(
        _ observed: Date?,
        savedAt: Date,
        tolerance: TimeInterval
    ) -> Date? {
        guard let observed,
              observed.timeIntervalSinceReferenceDate.isFinite,
              savedAt.timeIntervalSinceReferenceDate.isFinite else { return nil }
        let ahead = observed.timeIntervalSince(savedAt)
        if ahead <= 0 { return observed }
        if tolerance > 0, ahead <= tolerance { return savedAt }
        return nil
    }

    private static func validObservation(_ observed: Date, savedAt: Date) -> Bool {
        observed.timeIntervalSinceReferenceDate.isFinite
            && savedAt.timeIntervalSinceReferenceDate.isFinite
            && observed <= savedAt
    }

    static func evaluateEventFaceState(
        game: WatchSelectedGame?,
        eventID: Int,
        isAdmitted: Bool,
        savedAt: Date,
        clockSkewTolerance: TimeInterval = defaultGameClockSkewTolerance,
        containerAvailable: Bool = true
    ) -> WatchFaceDisplayState13339 {
        let targetID = max(1, game?.id ?? eventID)
        let title: String = {
            guard let game else { return "Chosen game" }
            let awayFull = game.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)
            let homeFull = game.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
            let awayShort = (game.awayCompactIdentity?.isValid == true) ? game.awayCompactIdentity!.abbreviation : awayFull
            let homeShort = (game.homeCompactIdentity?.isValid == true) ? game.homeCompactIdentity!.abbreviation : homeFull
            if !awayFull.isEmpty, !homeFull.isEmpty {
                let full = "\(awayFull) at \(homeFull)"
                return full.count <= 22 ? full : "\(awayShort) at \(homeShort)"
            }
            return homeFull.isEmpty ? "Chosen game" : homeFull
        }()
        guard containerAvailable else {
            return .unavailable(
                WatchFaceStatusPayload13339(
                    targetID: targetID,
                    title: title,
                    reason: .sharedStorageUnavailable,
                    updatedAt: savedAt
                ),
                snapshot: nil
            )
        }
        guard let game else {
            return .unavailable(
                WatchFaceStatusPayload13339(
                    targetID: targetID,
                    title: title,
                    reason: .waitingForUpdate,
                    updatedAt: savedAt
                ),
                snapshot: nil
            )
        }
        if game.isFinal {
            if let snap = snapshot(game: game, savedAt: savedAt, clockSkewTolerance: clockSkewTolerance),
               snap.validatedRectangularReading(now: savedAt) != nil {
                if WatchMatchupReading217.finalHasPassed(snap, now: savedAt) {
                    return .unavailable(
                        WatchFaceStatusPayload13339(
                            targetID: targetID,
                            title: title,
                            reason: .finalEnded,
                            updatedAt: savedAt
                        ),
                        snapshot: snap
                    )
                }
                return .ready(snap)
            }
            return .unavailable(
                WatchFaceStatusPayload13339(
                    targetID: targetID,
                    title: title,
                    reason: .waitingForUpdate,
                    updatedAt: savedAt
                ),
                snapshot: nil
            )
        }
        let statusLower = (game.status ?? "").lowercased()
        guard ["live", "scheduled", "upcoming", "in_progress", "pregame"].contains(statusLower) else {
            return .unavailable(
                WatchFaceStatusPayload13339(
                    targetID: targetID,
                    title: title,
                    reason: .statusUnsupported,
                    updatedAt: savedAt
                ),
                snapshot: nil
            )
        }
        guard isAdmitted, game.showsForecast, game.homeProbabilityText != nil else {
            let scoreOnlySnap = snapshot(game: game, savedAt: savedAt, clockSkewTolerance: clockSkewTolerance)
            return .unavailable(
                WatchFaceStatusPayload13339(
                    targetID: targetID,
                    title: title,
                    reason: .noLiveOdds,
                    updatedAt: savedAt
                ),
                snapshot: scoreOnlySnap
            )
        }
        if let snap = snapshot(game: game, savedAt: savedAt, clockSkewTolerance: clockSkewTolerance),
           snap.validatedRectangularReading(now: savedAt) != nil {
            return .ready(snap)
        }
        return .unavailable(
            WatchFaceStatusPayload13339(
                targetID: targetID,
                title: title,
                reason: .waitingForUpdate,
                updatedAt: savedAt
            ),
            snapshot: nil
        )
    }
}

nonisolated enum WatchFaceDisplayState13339: Sendable {
    case noSelection
    case ready(WatchComplicationSnapshot)
    case unavailable(WatchFaceStatusPayload13339, snapshot: WatchComplicationSnapshot? = nil)

    var snapshot: WatchComplicationSnapshot? {
        switch self {
        case .noSelection: return nil
        case .ready(let s): return s
        case .unavailable(_, let s): return s
        }
    }

    var unavailableStatus: WatchFaceStatusPayload13339? {
        switch self {
        case .noSelection, .ready: return nil
        case .unavailable(let status, _): return status
        }
    }

    var appNotice: String? {
        unavailableStatus?.reason.appNotice
    }
}

nonisolated enum WatchComplicationPublisher {
    static var hasSharedContainer: Bool {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch") != nil
    }

    /// Shared storage is unavailable until the app and extension are properly entitled.
    /// Never substitute separate standard defaults and pretend data was shared.
    static func publish(game: WatchSelectedGame?, savedAt: Date?) {
        let snapshot = game.flatMap { game in savedAt.flatMap { WatchComplicationProjection.snapshot(game: game, savedAt: $0) } }
        publishSnapshot(snapshot)
    }

    static func publishSnapshot(
        _ snapshot: WatchComplicationSnapshot?,
        unavailableStatus: WatchFaceStatusPayload13339? = nil,
        forceReload: Bool = false
    ) {
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        let snapChanged = write(snapshot, to: directory)
        let statusChanged = writeUnavailableStatus(unavailableStatus, to: directory)
        fetchMatchupCrests(for: snapshot)
        guard snapChanged || statusChanged || forceReload else { return }
        #if canImport(WidgetKit)
        WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")
        #endif
    }

    static func publishState(_ state: WatchFaceDisplayState13339, forceReload: Bool = false) {
        publishSnapshot(state.snapshot, unavailableStatus: state.unavailableStatus, forceReload: forceReload)
    }

    /// Direction 217: the complication can't fetch while it draws, so the app
    /// saves both crests to the shared container and reloads the slot once a
    /// new one lands. A crest that never arrives leaves the abbreviation disc.
    static func fetchMatchupCrests(for snapshot: WatchComplicationSnapshot?) {
        guard let snapshot, let facts = snapshot.matchup, let reading = snapshot.rectangularReading,
              let home = reading.home, let away = reading.away else { return }
        let wanted = [(teamID: home.teamID, logo: facts.homeLogo), (teamID: away.teamID, logo: facts.awayLogo)]
        let needsWork = wanted.contains { entry in
            guard let existing = WatchMatchupCrests217.data(teamID: entry.teamID) else {
                return entry.logo != nil
            }
            return !WatchMatchupCrests217.isWithinPixelLimit(existing)
        }
        guard needsWork else { return }
        Task.detached(priority: .utility) {
            guard await WatchMatchupCrests217.fetchMissing(wanted) else { return }
            #if canImport(WidgetKit)
            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")
            #endif
        }
    }

    @discardableResult
    static func writeUnavailableStatus(_ status: WatchFaceStatusPayload13339?, to directory: URL?) -> Bool {
        guard let directory else { return false }
        let url = directory.appendingPathComponent(WatchFaceStatusPayload13339.filename)
        do {
            let valid = status.flatMap { $0.isValid ? $0 : nil }
            if let valid {
                if let existing = WatchFaceStatusPayload13339.read(from: directory),
                   existing.version == valid.version,
                   existing.targetID == valid.targetID,
                   existing.title == valid.title,
                   existing.reason == valid.reason {
                    return false
                }
                let data = try JSONEncoder().encode(valid)
                try data.write(to: url, options: .atomic)
                return true
            } else {
                let tombstone = Data("{}".utf8)
                if let handle = try? FileHandle(forReadingFrom: url) {
                    defer { try? handle.close() }
                    if (try? handle.read(upToCount: 3)) == tombstone { return false }
                } else {
                    return false
                }
                try tombstone.write(to: url, options: .atomic)
                return true
            }
        } catch {
            return false
        }
    }

    /// Returns true only when shared bytes changed; unchanged observations need no reload.
    @discardableResult
    static func write(_ snapshot: WatchComplicationSnapshot?, to directory: URL?, now: Date = Date()) -> Bool {
        guard let directory else { return false }
        let url = directory.appendingPathComponent("selected-game.json")
        do {
            let valid = snapshot.flatMap { $0.isValid(now: now) ? $0 : nil }
            if let valid, let existing = WatchComplicationSnapshot.read(from: directory, now: now),
               existing.version == valid.version, existing.eventID == valid.eventID,
               existing.title == valid.title, existing.detail == valid.detail,
               existing.observedAt == valid.observedAt,
               existing.circularReading == valid.circularReading,
               (valid.rectangularReading == nil || existing.rectangularReading == valid.rectangularReading),
               (valid.matchup == nil || existing.matchup == valid.matchup) {
                return false // A newer fetch alone is not a newer reading.
            }
            // A tombstone replaces the previous reading atomically on selection change.
            let data = try valid.map { try JSONEncoder().encode($0) } ?? Data("{}".utf8)
            if valid == nil, let handle = try? FileHandle(forReadingFrom: url) {
                defer { try? handle.close() }
                if (try? handle.read(upToCount: 3)) == data { return false }
            }
            try data.write(to: url, options: .atomic)
            return true
        } catch { return false }
    }
}
