import Foundation

/// #11985 — One game per team per 20-card Discover page unless BOTH games are
/// live or starting within the hour (`<= 3600s`). When a team appears in two
/// active/scheduled single-game cards on the same page and they are not both
/// live or within the hour, the nearer game keeps (or takes) the seat on that
/// page and the later game yields its seat to the next page.
///
/// Respects #11984 (`frozenPrefixCount`): cards already painted on screen are
/// never moved or displaced; any later-arriving duplicate for a team already
/// seated on that page yields forward without reshuffling the reader's view.
/// Respects #1091: yielded games move to the next page (or the tail of a short
/// `< pageSize` deck) — never dropped into an empty feed.
enum DiscoverPageTeamSeat11985 {

    static let defaultPageSize = 20
    static let imminentWindowSeconds: TimeInterval = 3600

    private struct SeatedEntry {
        let outputIndex: Int
        let event: FeedEventData
        let isFrozen: Bool
        let isImminent: Bool
    }

    /// Applies the per-page one-game-per-team rule across `items`.
    static func seatItems(
        _ items: [DiscoverGroupedItem],
        now: Date = Date(),
        pageSize: Int = defaultPageSize,
        frozenPrefixCount: Int = 0
    ) -> [DiscoverGroupedItem] {
        guard pageSize > 0, items.count > 1 else { return items }
        let clampedFrozen = min(max(0, frozenPrefixCount), items.count)
        var output = Array(items.prefix(clampedFrozen))
        var pool = Array(items.dropFirst(clampedFrozen))

        while !pool.isEmpty {
            let pageStart = (output.count / pageSize) * pageSize
            var seatsByTeam = buildSeatMap(
                in: output,
                range: pageStart..<output.count,
                frozenPrefixCount: clampedFrozen,
                now: now
            )
            var deferred: [DiscoverGroupedItem] = []
            var idx = 0

            while idx < pool.count {
                if output.count - pageStart >= pageSize {
                    deferred.append(contentsOf: pool[idx...])
                    break
                }

                let candidate = pool[idx]
                idx += 1

                guard let event = activeSingleEvent(for: candidate) else {
                    output.append(candidate)
                    continue
                }

                let teams = teamKeys(for: event)
                guard !teams.isEmpty else {
                    output.append(candidate)
                    continue
                }

                let candImminent = isLiveOrWithinHour(event, now: now)
                let conflicts = conflictingOutputIndices(
                    for: teams,
                    candImminent: candImminent,
                    seatsByTeam: seatsByTeam
                )

                if conflicts.isEmpty {
                    let newIndex = output.count
                    output.append(candidate)
                    recordSeat(
                        outputIndex: newIndex,
                        event: event,
                        isFrozen: false,
                        isImminent: candImminent,
                        into: &seatsByTeam
                    )
                    continue
                }

                // If `candidate` conflicts with exactly ONE unfrozen seat on this
                // page and `candidate` is strictly nearer than that seated game,
                // the nearer game takes that seat and the later game yields.
                if conflicts.count == 1,
                   let displacedIndex = conflicts.first,
                   displacedIndex >= clampedFrozen,
                   let displacedEvent = activeSingleEvent(for: output[displacedIndex]),
                   isStrictlyNearer(event, than: displacedEvent, now: now) {
                    let yieldedItem = output[displacedIndex]
                    output[displacedIndex] = candidate
                    seatsByTeam = buildSeatMap(
                        in: output,
                        range: pageStart..<output.count,
                        frozenPrefixCount: clampedFrozen,
                        now: now
                    )
                    deferred.append(yieldedItem)
                } else {
                    deferred.append(candidate)
                }
            }

            if output.count - pageStart < pageSize {
                // Fewer non-conflicting cards exist than needed to complete this
                // page (#1091): append deferred games at the tail sorted nearer-first
                // so nothing is dropped and nearer games still lead.
                let orderedTail = sortDeferredNearerFirst(deferred, now: now)
                output.append(contentsOf: orderedTail)
                break
            }

            pool = deferred
        }

        return output
    }

    // MARK: - Classification Helpers

    static func activeSingleEvent(for item: DiscoverGroupedItem) -> FeedEventData? {
        guard case .single(let feedItem) = item,
              feedItem.type == "event",
              let event = feedItem.event else {
            return nil
        }
        if EventState.isFinished(event.status) {
            return nil
        }
        if event.status == "suspended"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate) {
            return nil
        }
        return event
    }

    static func teamKeys(for event: FeedEventData) -> [String] {
        let sport = (event.sport ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        var keys: [String] = []
        for rawName in [event.awayTeam, event.homeTeam] {
            let norm = normalizeTeamName(rawName)
            guard !norm.isEmpty else { continue }
            let key = "\(sport)|\(norm)"
            if !keys.contains(key) {
                keys.append(key)
            }
        }
        return keys
    }

    static func isLiveOrWithinHour(_ event: FeedEventData, now: Date) -> Bool {
        if event.status == "live" {
            return true
        }
        guard event.startIsTbd != true, let start = event.commenceTime?.asDate else {
            return false
        }
        return start.timeIntervalSince(now) <= imminentWindowSeconds
    }

    static func isStrictlyNearer(_ lhs: FeedEventData, than rhs: FeedEventData, now: Date) -> Bool {
        let lhsLive = lhs.status == "live"
        let rhsLive = rhs.status == "live"
        if lhsLive != rhsLive {
            return lhsLive
        }
        let lhsDate = lhs.startIsTbd == true ? nil : lhs.commenceTime?.asDate
        let rhsDate = rhs.startIsTbd == true ? nil : rhs.commenceTime?.asDate
        switch (lhsDate, rhsDate) {
        case let (l?, r?):
            return l < r
        case (_?, nil):
            return true
        case (nil, _?):
            return false
        case (nil, nil):
            return false
        }
    }

    // MARK: - Private Helpers

    private static func normalizeTeamName(_ raw: String) -> String {
        raw.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func buildSeatMap(
        in output: [DiscoverGroupedItem],
        range: Range<Int>,
        frozenPrefixCount: Int,
        now: Date
    ) -> [String: [SeatedEntry]] {
        var map: [String: [SeatedEntry]] = [:]
        for idx in range {
            guard let event = activeSingleEvent(for: output[idx]) else { continue }
            recordSeat(
                outputIndex: idx,
                event: event,
                isFrozen: idx < frozenPrefixCount,
                isImminent: isLiveOrWithinHour(event, now: now),
                into: &map
            )
        }
        return map
    }

    private static func recordSeat(
        outputIndex: Int,
        event: FeedEventData,
        isFrozen: Bool,
        isImminent: Bool,
        into map: inout [String: [SeatedEntry]]
    ) {
        let entry = SeatedEntry(
            outputIndex: outputIndex,
            event: event,
            isFrozen: isFrozen,
            isImminent: isImminent
        )
        for key in teamKeys(for: event) {
            map[key, default: []].append(entry)
        }
    }

    private static func conflictingOutputIndices(
        for teams: [String],
        candImminent: Bool,
        seatsByTeam: [String: [SeatedEntry]]
    ) -> Set<Int> {
        var indices = Set<Int>()
        for key in teams {
            for seat in seatsByTeam[key] ?? [] {
                if !(seat.isImminent && candImminent) {
                    indices.insert(seat.outputIndex)
                }
            }
        }
        return indices
    }

    private static func sortDeferredNearerFirst(
        _ items: [DiscoverGroupedItem],
        now: Date
    ) -> [DiscoverGroupedItem] {
        items.enumerated().sorted { lhs, rhs in
            guard let lEvent = activeSingleEvent(for: lhs.element),
                  let rEvent = activeSingleEvent(for: rhs.element) else {
                return lhs.offset < rhs.offset
            }
            if isStrictlyNearer(lEvent, than: rEvent, now: now) {
                return true
            }
            if isStrictlyNearer(rEvent, than: lEvent, now: now) {
                return false
            }
            return lhs.offset < rhs.offset
        }.map(\.element)
    }
}
