import Foundation

/// A source bar is its own quote, not the blend in `frame.p`. Keep its clock
/// and value together, and only update sources the served detail admitted.
nonisolated enum LiveEventSourceReconciliation {
    static func applying(
        _ frame: LiveStreamFrame, to event: EventDetail, newerThan acceptedAt: Date? = nil
    ) -> EventDetail? {
        guard event.id == frame.eventId, event.status == "live", frame.status == "live",
              let key = frame.source, key != "final_result",
              WinProbSourceCatalog.realSourceKeys.contains(key),
              let quote = frame.sourceValue, quote.isFinite, (0...1).contains(quote),
              let stamp = frame.updatedAt, let pushedAt = stamp.asDate,
              var entry = event.winProbabilitySources?[key],
              let served = entry.value?.doubleValue, served.isFinite, (0...1).contains(served),
              let servedAt = entry.updatedAt?.asDate, pushedAt > servedAt,
              acceptedAt.map({ pushedAt > $0 }) ?? true else { return nil }
        entry.value = .number(quote)
        entry.updatedAt = stamp
        var updated = event
        updated.winProbabilitySources?[key] = entry
        return updated
    }

    static func observationDates(in event: EventDetail) -> [String: Date] {
        var dates: [String: Date] = [:]
        for (key, entry) in event.winProbabilitySources ?? [:] {
            guard key != "final_result", WinProbSourceCatalog.realSourceKeys.contains(key),
                  let value = entry.value?.doubleValue, value.isFinite, (0...1).contains(value),
                  let date = entry.updatedAt?.asDate else { continue }
            dates[key] = date
        }
        return dates
    }

    /// Run after hero reconciliation: updating a source clock first must not
    /// make an old REST blend appear newer. Each source keeps its own frame,
    /// since a subsequent publication from another venue does not replace it.
    static func reconciling(
        _ frames: inout [String: LiveStreamFrame], over polled: EventDetail,
        streamRecoverable: Bool
    ) -> EventDetail {
        guard streamRecoverable, polled.status == "live" else {
            frames.removeAll()
            return polled
        }
        var reconciled = polled
        for (key, frame) in frames {
            if let updated = applying(frame, to: reconciled) {
                reconciled = updated
            } else {
                // REST owns removal/refusal, unknown clocks and equally/newer
                // quotes. Retire the old frame so a later cache hit cannot
                // resurrect it; display metadata always comes from this REST.
                frames.removeValue(forKey: key)
            }
        }
        return reconciled
    }
}
