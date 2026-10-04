import Foundation

/// #10239 / #10455 — the event page's admission for the projected final-points
/// module. Twin of web's `projectedFinalPointsMount`
/// (`frontend/components/event/ProjectedFinalPointsModule.tsx`).
///
/// FINISHED NFL ONLY. A finished game's `/history` is served whole (the route's
/// cutoff is `None`), so no row is a cutoff re-stamp and `requestCutoffAt` is
/// nil. A live or pregame read asks for 168 hours and the route re-stamps the
/// row still valid at that cutoff with no marker; that heuristic is not
/// admitted here, so those games mount nothing.
///
/// - The book is the deterministic picker's (most usable pairs, ties to the
///   first key in sorted order), and only a book `SourceLabels` can name.
/// - The score floor is the first Q1 boundary a named instrument OBSERVED. It
///   is not a kickoff, so `kickoffAt` stays nil; without it nothing mounts.
/// - `asOf` is the recorded completion, so the view does not move with the
///   reader's clock.
/// - The final score is the page's own (the pair the hero prints), appended as
///   the last ACTUAL step at completion. `score_history`'s last row is only the
///   last score recorded (14780549: 26–7 before the extra point), and it is
///   never joined to the forecast series.
enum ProjectedFinalPointsMount {
    private static let observingMarkerSources: Set<String> = ["espn_state", "espn_box", "statpal", "win_prob"]
    private static let periodStartPrecisions: Set<String> = ["first_seen", "boundary_observed"]

    @MainActor
    static func input(sportKey: String?, eventStatus: String?, history: EventHistoryResponse?,
                      finalHome: Int?, finalAway: Int?) -> ProjectedFinalPointsSeries.Input? {
        guard sportKey == "americanfootball_nfl",
              EventState.isFinished(eventStatus),
              let history,
              // The no-cutoff reading below is the FINISHED history's branch;
              // a page that reads final over a live/scheduled/unlabelled
              // history may carry cutoff re-stamps, so it refuses.
              EventState.isFinished(history.status),
              let finalAt = history.completedAt?.asDate,
              let sourceKey = pickSportsbook(history.bookmakerHistory),
              let floor = firstRecordedGameStateAt(history.periodMarkers, sportKey: sportKey)
        else { return nil }
        let pairs: [ProjectedFinalPointsSeries.Pair] = (history.bookmakerHistory?[sourceKey] ?? []).compactMap { row in
            guard let at = row.timestamp.asDate else { return nil }
            return .init(at: at, home: row.projectedHomeScore, away: row.projectedAwayScore,
                         homeProbability: row.homeProbability, kind: pairKind(row.kind))
        }
        var actuals: [ProjectedFinalPointsSeries.Actual] = (history.scoreHistory ?? []).compactMap { row in
            guard let at = row.timestamp.asDate else { return nil }
            return .init(at: at, home: Double(row.homeScore), away: Double(row.awayScore))
        }
        if let finalHome, let finalAway, finalHome >= 0, finalAway >= 0 {
            actuals.removeAll { $0.at >= finalAt }
            actuals.append(.init(at: finalAt, home: Double(finalHome), away: Double(finalAway)))
        }
        let input = ProjectedFinalPointsSeries.Input(
            sportKey: "americanfootball_nfl", sourceKey: sourceKey,
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: pairs, actuals: actuals, kickoffAt: nil, scoreObservationStartAt: floor,
            finalAt: finalAt, asOf: finalAt, windowStartAt: nil, requestCutoffAt: nil)
        return ProjectedFinalPointsSeries.build(input) == nil ? nil : input
    }

    /// Only literal `"recorded"`, or no marker at all (behind the
    /// finished-history guard: that route had no cutoff to re-stamp at), is
    /// recorded. `"synthetic"` and any string this build does not know are
    /// synthetic, which the utility refuses.
    static func pairKind(_ served: String?) -> ProjectedFinalPointsSeries.Kind {
        served == nil || served == "recorded" ? .recorded : .synthetic
    }

    /// The named book with the most usable full-game pairs; ties go to the
    /// first key in sorted order (web `pickProjectionSportsbook`).
    @MainActor
    static func pickSportsbook(_ books: [String: [BookmakerHistoryPoint]]?) -> String? {
        var best: String?
        var bestCount = 0
        for key in (books ?? [:]).keys.sorted() where SourceLabels.sportsbookName(for: key) != nil {
            let count = (books?[key] ?? []).filter {
                guard let home = $0.projectedHomeScore, let away = $0.projectedAwayScore else { return false }
                return home.isFinite && home >= 0 && away.isFinite && away >= 0
            }.count
            if count > bestCount { best = key; bestCount = count }
        }
        return best
    }

    /// Earliest `not_before` of an OBSERVED first-quarter start marker (web
    /// `firstRecordedGameStateAt`). Estimated, unsourced and first-score
    /// markers are refused.
    static func firstRecordedGameStateAt(_ markers: [PeriodMarkerPayload]?, sportKey: String?) -> Date? {
        (markers ?? []).compactMap { marker -> Date? in
            guard let source = marker.source, observingMarkerSources.contains(source),
                  let precision = marker.precision, periodStartPrecisions.contains(precision),
                  let period = marker.period, PeriodLabel.normalize(period, sport: sportKey) == "Q1"
            else { return nil }
            return marker.notBefore?.asDate
        }.min()
    }
}
