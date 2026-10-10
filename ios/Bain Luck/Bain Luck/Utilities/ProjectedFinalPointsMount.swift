import Foundation

/// #10239 / #10455 / #10478 — the event page's admission for the projected
/// final-points module. Twin of web's `projectedFinalPointsMount`
/// (`frontend/components/event/ProjectedFinalPointsModule.tsx`).
///
/// The leagues `ProjectedFinalPointsSeries.leagues` names (NFL, college
/// football, NBA, WNBA, men's and women's college basketball), before, during
/// and after the game. It mounts nothing unless every input below is present.
///
/// - The page's own sport key reaches the series unchanged; it picks the
///   league's first period and axis step. Basketball's during/after phases
///   need an observed first-period start, which the server serves only for
///   football today (`period_markers.TRANSITION_SPORT_PREFIXES`), so a live or
///   finished basketball page keeps its Score Differential card until it does.
///
/// - The page and the history must be in the same phase. The history carries
///   its own served `status`; a finished page over a live, scheduled or
///   status-less history, or a live page over a finished one, is refused, never
///   reconciled by picking a side. A completion stamp on a history whose page
///   is not finished is refused too: it never turns a live chart into "after".
/// - Rows count by their served provenance (#10461): `kind == "recorded"` AND
///   an `observed_at` that is a strict offset-bearing instant inside the row's
///   own displayed minute. Such a row is placed at `observed_at`, so `asOf` and
///   a scrub cursor compare against the capture itself. `synthetic`, an unknown
///   or mistyped kind, a missing or malformed `observed_at` are refused.
/// - A row with no provenance at all (a payload from before the contract) is
///   read as recorded ONLY on a finished page over a finished history, which is
///   served whole (the route's cutoff is `None`), so no row can be a re-stamp.
///   Anywhere else it is refused: a nil kind is never promoted globally.
/// - `asOf` is the recorded completion after the game, so the view does not
///   move with the reader's clock. Before and during, it is the reader's clock
///   the caller supplies; without one those phases mount nothing.
/// - The book is the deterministic picker's (most pairs the series would DRAW,
///   ties to the first key in sorted order), and only a book `SourceLabels` can
///   name. Each book is scored through `ProjectedFinalPointsSeries.build` with
///   the same floor, actuals, final and `asOf`, so a row the series refuses
///   (outside the window, at or past the final, contradicting the moneyline,
///   below the actual score) never counts. Counting raw or merely admitted rows
///   would let a book of refused rows hide one with real readings.
/// - Before the game there is no score floor, no actual score and no final
///   boundary, whatever markers or scores the history retains. During and
///   after, the score floor is the first first-period boundary (Q1, or 1H in
///   men's college basketball) a named instrument OBSERVED. It is not a kickoff, so `kickoffAt` stays nil; without it
///   nothing mounts.
/// - After the game the final score is the page's own (the pair the hero
///   prints), appended as the last ACTUAL step at completion. `score_history`'s
///   last row is only the last score recorded (14780549: 26–7 before the extra
///   point), and it is never joined to the forecast series.
enum ProjectedFinalPointsMount {
    private static let observingMarkerSources: Set<String> = ["espn_state", "espn_box", "statpal", "win_prob"]
    private static let periodStartPrecisions: Set<String> = ["first_seen", "boundary_observed"]
    private static let recordedKind = "recorded"

    enum Phase: Equatable { case before, during, after }

    /// The phase a status names, or nil for one this module does not mount
    /// (postponed, suspended, cancelled, unknown, missing).
    static func phase(of status: String?) -> Phase? {
        if EventState.isFinished(status) { return .after }
        if status == "live" { return .during }
        if status == "scheduled" { return .before }
        return nil
    }

    /// How a served row may be admitted as recorded evidence. The picker and
    /// the input share it, so a book is never picked on rows the chart refuses.
    struct Admission {
        /// A row with no provenance may be read the pre-contract way: a
        /// finished page over a finished history served whole.
        let legacyRowsAdmitted: Bool
        /// Nothing captured after this instant counts.
        let asOf: Date
    }

    /// `asOf` is the reader's clock for a scheduled or live page, taken when the
    /// history arrived. Nil keeps the finished-only mount: before and during
    /// refuse rather than borrow a clock nobody supplied.
    @MainActor
    static func input(sportKey: String?, eventStatus: String?, history: EventHistoryResponse?,
                      finalHome: Int?, finalAway: Int?, asOf readerNow: Date? = nil) -> ProjectedFinalPointsSeries.Input? {
        guard let sportKey, ProjectedFinalPointsSeries.leagues[sportKey] != nil,
              let pagePhase = Self.phase(of: eventStatus),
              let history,
              // A missing history status says nothing, so it refuses too.
              Self.phase(of: history.status) == pagePhase
        else { return nil }
        let finalAt: Date?
        let asOf: Date
        if pagePhase == .after {
            guard let completed = history.completedAt?.asDate else { return nil }
            finalAt = completed
            asOf = completed
        } else {
            // A completion stamp on a game the page and history both call
            // unfinished is stale or early: refused, never read as the end.
            guard history.completedAt == nil,
                  let readerNow, readerNow.timeIntervalSince1970.isFinite else { return nil }
            finalAt = nil
            asOf = readerNow
        }
        let admission = Admission(legacyRowsAdmitted: pagePhase == .after, asOf: asOf)
        var scoreFloor: Date?
        if pagePhase != .before {
            // A floor after the reader's clock is not yet a game state they can see.
            guard let observed = firstRecordedGameStateAt(history.periodMarkers, sportKey: sportKey),
                  observed <= asOf else { return nil }
            scoreFloor = observed
        }
        var actuals: [ProjectedFinalPointsSeries.Actual] = []
        if pagePhase != .before {
            actuals = (history.scoreHistory ?? []).compactMap { row in
                guard let at = row.timestamp.asDate else { return nil }
                return .init(at: at, home: Double(row.homeScore), away: Double(row.awayScore))
            }
        }
        if pagePhase == .after, let finalAt, let finalHome, let finalAway, finalHome >= 0, finalAway >= 0 {
            actuals.removeAll { $0.at >= finalAt }
            actuals.append(.init(at: finalAt, home: Double(finalHome), away: Double(finalAway)))
        }
        func seriesInput(_ sourceKey: String) -> ProjectedFinalPointsSeries.Input {
            let pairs: [ProjectedFinalPointsSeries.Pair] = (history.bookmakerHistory?[sourceKey] ?? []).compactMap { row in
                let admitted = admit(row, admission: admission)
                guard let at = admitted.at else { return nil }
                return .init(at: at, home: row.projectedHomeScore, away: row.projectedAwayScore,
                             homeProbability: row.homeProbability, kind: admitted.kind)
            }
            return ProjectedFinalPointsSeries.Input(
                sportKey: sportKey, sourceKey: sourceKey,
                basis: .sameBookSameCaptureFullGameSpreadAndTotal,
                pairs: pairs, actuals: actuals, kickoffAt: nil, scoreObservationStartAt: scoreFloor,
                finalAt: finalAt, asOf: asOf, windowStartAt: nil, requestCutoffAt: nil)
        }
        guard let sourceKey = pickSportsbook(history.bookmakerHistory, seriesInput: seriesInput) else { return nil }
        return seriesInput(sourceKey)
    }

    /// #10549 — the page's ONE projected-points decision (web #10539's
    /// `useProjectedFinalPointsMount`). True only when `input` admitted a book
    /// AND that book's series draws, so the chart that replaces the Score
    /// Differential card is the chart the page actually renders. Every refusal
    /// (sport, phase, provenance, no observed floor, nothing drawable) keeps the
    /// differential: it is never hidden on the sport alone.
    @MainActor
    static func replacesScoreDifferential(_ input: ProjectedFinalPointsSeries.Input?) -> Bool {
        input.flatMap(ProjectedFinalPointsSeries.build) != nil
    }

    /// One served row's admission: the kind it is read as and the instant it
    /// is placed at (web `admitRow`). Explicit provenance decides whenever any
    /// of it is present; a row with none is recorded only when the admission
    /// allows legacy rows. Refused rows keep their displayed minute and are
    /// marked `.synthetic`, which the utility never admits.
    static func admit(_ row: BookmakerHistoryPoint, admission: Admission)
        -> (kind: ProjectedFinalPointsSeries.Kind, at: Date?) {
        let displayed = row.timestamp.asDate
        guard row.servesProvenance else {
            return (admission.legacyRowsAdmitted ? .recorded : .synthetic, displayed)
        }
        // Strict parse: an offset-less local time or an impossible day is not
        // a capture, even when a lenient formatter would land it on the minute.
        guard row.kind == recordedKind,
              let observed = row.observedAt.flatMap(ISO8601Stamp.date),
              let displayed,
              // The displayed minute is the capture truncated to the minute.
              (observed.timeIntervalSince1970 / 60).rounded(.down) * 60 == displayed.timeIntervalSince1970
        else { return (.synthetic, displayed) }
        return (.recorded, observed)
    }

    /// The named book whose series draws the most points; ties go to the first
    /// key in sorted order (web `pickProjectionSportsbook`). A book is scored by
    /// `build` over the caller's own input, so every series refusal applies to
    /// the count, and a book that charts nothing never wins.
    @MainActor
    static func pickSportsbook(_ books: [String: [BookmakerHistoryPoint]]?,
                               seriesInput: (String) -> ProjectedFinalPointsSeries.Input) -> String? {
        var best: String?
        var bestCount = 0
        for key in (books ?? [:]).keys.sorted() where SourceLabels.sportsbookName(for: key) != nil {
            let count = ProjectedFinalPointsSeries.build(seriesInput(key))?.segments.reduce(0) { $0 + $1.count } ?? 0
            if count > bestCount { best = key; bestCount = count }
        }
        return best
    }

    /// Earliest `not_before` of an OBSERVED start marker of the league's first
    /// period (web `firstRecordedGameStateAt`). Estimated, unsourced and
    /// first-score markers are refused, and so is another period vocabulary:
    /// a men's college basketball game never opens on a "Q1". An unlisted
    /// sport has no first period here.
    static func firstRecordedGameStateAt(_ markers: [PeriodMarkerPayload]?, sportKey: String?) -> Date? {
        guard let firstPeriod = sportKey.flatMap({ ProjectedFinalPointsSeries.leagues[$0]?.firstPeriod })
        else { return nil }
        return (markers ?? []).compactMap { marker -> Date? in
            guard let source = marker.source, observingMarkerSources.contains(source),
                  let precision = marker.precision, periodStartPrecisions.contains(precision),
                  let period = marker.period, PeriodLabel.normalize(period, sport: sportKey) == firstPeriod
            else { return nil }
            return marker.notBefore?.asDate
        }.min()
    }
}
