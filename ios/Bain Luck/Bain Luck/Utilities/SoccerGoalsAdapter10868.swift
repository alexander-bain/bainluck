import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE GOAL
/// MILESTONES STORY.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the goal milestones card prints each
/// original full-match total's pre-match chance of reaching N+ goals, the goals
/// so far against those milestones and, after the final, each original's own
/// result — or that slot's own words.
///
/// Rules, each an existing owner's:
///
///   - milestones   the owner's admitted full-match total markets
///                  (`SoccerPropReadingAdapter10868.Markets.goals`), in that
///                  order; for each, its one OVER-side served row
///                  (`QuestionCatalog9483.lineSide`, gotcha #17) with a finite
///                  threshold. An Under-only market adds no milestone — never a
///                  complement.
///   - N+           `MLBMilestoneCard11284.milestone` ("count > X.5 is ≥
///                  floor(X.5) + 1"): Over 2.5 is 3+.
///   - readings     part three's rules (`SoccerPropReadingAdapter10868`). A
///                  totals row's clock can be a sibling's (served
///                  `observed_at_basis`, not decoded), so a totals quote is never
///                  this card's in-play chance, nor its pre-match chance before
///                  the start; once started, the stored pre-match pin is.
///   - own clock    the ONE way a totals row's clock counts as its own: the
///                  owner names its market in `ownClock`
///                  (`SoccerPropReadingAdapter10868.Markets.ownClockGoals`) from
///                  the producer's decoded `observed_at_basis`. Then, and only
///                  then, part three reads it like any own-clock row — still
///                  recent-only before kickoff, still at or after the start and
///                  recent during play. Nothing here infers it from a value, a
///                  title or a time. MISSING OWNER INPUT: `GameMarketOutcome`
///                  does not decode `observed_at_basis` (Models/FuturesModels.swift,
///                  #9483, Native), so today no host can supply it.
///
/// Before kickoff this card is the soccer page's TOTAL GOAL OUTLOOK (Design's
/// approved route membership): hollow at-least stems (`.stems`), one per
/// admitted original, each with its own clock — never a fitted curve, a
/// distribution, a projected final or a complementary Under. A market the
/// venue serves only as an Under leg adds no stem (`QuestionCatalog9483`'s one
/// over-side rule, gotcha #17) — the reference's 7+/8+/9+ stems are such rows,
/// an explicit unpaid producer-contract question, not a gap filled here.
///   - reached      `PlayerPropsCardView.rungVerdict` on the goals so far —
///                  performance, never 100% and never a settlement.
///   - counts       `EventDetail.homeScore + awayScore`, dated only by
///                  `scoreObservedAt`.
///   - default      `PlayerPropsFamily.defaultTarget` over the printed
///                  pre-match chances (nearest even odds), as H3 opens.
///
/// No projected total is admitted for soccer (no owner), so `projection` is nil.
/// The host passes the event, `/game-markets`, the admission, now, the reader's
/// calendar and its held milestone; nothing here fetches.
enum SoccerGoalsAdapter10868 {
    typealias R = SoccerPropReadingAdapter10868

    enum Words {
        static let eyebrow = "TOTAL GOALS · EXPECTATIONS VS ACTUAL"
        static let beforeTitle = "How many goals?"
        static let liveTitle = "Goals so far against the milestones"
        static let finalTitle = "Final goals against the milestones"
        static let chartTitle = "Chance of reaching each total"
        static let axisTitle = "Total goals in the match"
        static let reachedSoFar = "Reached so far"
        static let scoreUnavailable = "Score unavailable"
        static let finalScoreUnavailable = "Final score unavailable"
        static let timingSuffix = "chance timing"
        static func unit(_ count: Int) -> String { count == 1 ? "goal" : "goals" }
    }

    /// Axis words on the fixed 0...1 scale — scale words, not chances, so not
    /// through `formatProbability` (which would print "<1%"/">99%").
    static let chanceTicks = [
        TotalMilestoneTick10868(value: 0, text: "0%"),
        TotalMilestoneTick10868(value: 0.5, text: "50%"),
        TotalMilestoneTick10868(value: 1, text: "100%"),
    ]

    /// The card, or nil when no admitted market serves an over-side milestone.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, admitted: [Int],
                      ownClock: Set<Int> = [], host: R.Host,
                      selectedMilestoneID: String? = nil) -> TotalMilestoneInput10868? {
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let goals = R.goals(event)
        var rows: [TotalMilestoneRow10868] = []
        var legs: [R.Leg] = []
        for marketID in admitted {
            let overs = R.legs(marketID, in: markets).filter {
                QuestionCatalog9483.lineSide($0.row) == .over && ($0.threshold?.isFinite ?? false)
            }
            // One original line per market; two over rows is not one milestone.
            guard overs.count == 1, let served = overs.first, let threshold = served.threshold else { continue }
            let leg = ownClock.contains(marketID) ? owningClock(served) : served
            rows.append(row(leg, threshold: threshold, event: event, phase: phase, goals: goals, host: host))
            legs.append(leg)
        }
        guard !rows.isEmpty else { return nil }

        let chosen = selectedMilestoneID
            ?? PlayerPropsFamily.defaultTarget(probabilities: rows.map { $0.before?.probability }).map { rows[$0].id }
        let top = max(rows.map(\.quantity).max() ?? 0, Double(goals?.total ?? 0))
        let quantityTicks = [TotalMilestoneTick10868(value: 0, text: "0")]
            + rows.map { TotalMilestoneTick10868(value: $0.quantity, text: $0.quantityLabel) }
        return TotalMilestoneInput10868(
            phase: phase.totalPhase,
            eyebrow: Words.eyebrow,
            title: phase == .before ? Words.beforeTitle : phase == .live ? Words.liveTitle : Words.finalTitle,
            chartTitle: Words.chartTitle,
            quantityAxisTitle: Words.axisTitle,
            milestones: rows,
            selectedMilestoneID: chosen,
            actual: actual(goals, event: event, phase: phase, host: host),
            projection: nil,
            quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: top + 1),
            quantityTicks: quantityTicks,
            chanceTicks: chanceTicks,
            timing: chosen.flatMap { id in timing(id, rows: rows, legs: legs, event: event, phase: phase, host: host) },
            markStyle: .stems)
    }

    /// The same leg with its clock counted as its own — only for a market the
    /// owner proved (`ownClock`). Every other field is the served leg's.
    static func owningClock(_ leg: R.Leg) -> R.Leg {
        R.Leg(marketID: leg.marketID, id: leg.id, label: leg.label, row: leg.row, contributors: leg.contributors,
              isWinner: leg.isWinner, resolutionSource: leg.resolutionSource, threshold: leg.threshold,
              clockIsOwn: true, option: leg.option)
    }

    // MARK: - One milestone

    static func row(_ leg: R.Leg, threshold: Double, event: EventDetail, phase: SoccerEventPagePhase10868,
                    goals: R.Goals?, host: R.Host) -> TotalMilestoneRow10868 {
        let count = MLBMilestoneCard11284.milestone(threshold)
        let label = "\(count)+"
        let before = R.pregame(leg, event: event, host: host)
        let reached = goals.map {
            PlayerPropsCardView.rungVerdict(servedActual: nil, servedHit: nil, threshold: threshold,
                                            boxActual: Double($0.total)).hit == true
        } ?? false
        let current: TotalMilestoneCurrent10868
        let performance: String?
        if phase == .live {
            current = reached ? .reached(Words.reachedSoFar) : liveCurrent(R.current(leg, event: event, host: host))
            performance = reached ? nil : goals.map { "\(max(1, count - $0.total)) more for \(label)" }
        } else {
            current = .unavailable(R.Words.inPlayUnavailable)
            performance = nil
        }
        let result: TotalMilestoneResult10868 = phase == .final ? finalResult(R.result(leg)) : .unconfirmed(R.Words.resultUnavailable)
        return TotalMilestoneRow10868(
            id: leg.id, quantity: Double(count), quantityLabel: label, title: "\(label) \(Words.unit(count))",
            before: before.observation.map { Self.observation($0) }, beforeMissing: before.words,
            current: current, performance: performance, result: result)
    }

    static func observation(_ o: R.Observation) -> TotalMilestoneObservation10868 {
        TotalMilestoneObservation10868(probability: o.probability, text: o.text, timeText: o.clock,
                                       accessibilityDetail: o.detail)
    }

    static func liveCurrent(_ current: R.Current) -> TotalMilestoneCurrent10868 {
        switch current {
        case .recorded(let o): .recorded(Self.observation(o), movement: nil)
        case .withheld(let words): .withheld(words)
        case .unavailable(let words): .unavailable(words)
        }
    }

    static func finalResult(_ result: R.Result) -> TotalMilestoneResult10868 {
        switch result {
        case .won(let words): .won(words)
        case .lost(let words): .lost(words)
        case .unconfirmed(let words): .unconfirmed(words)
        }
    }

    // MARK: - The count

    static func actual(_ goals: R.Goals?, event: EventDetail, phase: SoccerEventPagePhase10868,
                       host: R.Host) -> TotalMilestoneActual10868? {
        switch phase {
        case .before:
            return nil
        case .live, .final:
            let final = phase == .final
            guard let goals else { return .unavailable(final ? Words.finalScoreUnavailable : Words.scoreUnavailable) }
            return .count(TotalMilestoneCount10868(
                quantity: Double(goals.total), text: "\(goals.total)", unit: Words.unit(goals.total),
                clock: R.goalsClock(goals, final: final, host: host),
                ruleLabel: final ? "\(goals.total) final" : "\(goals.total) so far",
                accessibilityDetail: R.goalsDetail(goals, event: event, final: final, host: host)))
        }
    }

    // MARK: - Timing

    static func timing(_ id: String, rows: [TotalMilestoneRow10868], legs: [R.Leg], event: EventDetail,
                       phase: SoccerEventPagePhase10868, host: R.Host) -> TotalMilestoneTiming10868? {
        guard let index = rows.firstIndex(where: { $0.id == id }), rows.filter({ $0.id == id }).count == 1 else {
            return nil
        }
        typealias T = TotalMilestoneInput10868
        let row = rows[index]
        var lines = ["\(T.pregameTitle): \(row.before?.accessibilityDetail ?? row.beforeMissing)"]
        if phase == .live {
            switch row.current {
            case .recorded(let o, _): lines.append("\(T.recordedTitle): \(o.accessibilityDetail)")
            case .unavailable(let words), .withheld(let words): lines.append("\(T.currentStatusTitle): \(words)")
            case .reached(let words): lines.append("\(T.actualSoFarTitle): \(words)")
            }
        }
        if phase == .final {
            let venue = row.result.isAdmitted ? SourceLabels.label(for: legs[index].row.source) : nil
            lines.append(SoccerMatchPageAdapter10868.joined(["\(T.resultTitle): \(row.result.text)",
                                                             venue.map { "settled by \($0)" }]) ?? row.result.text)
        }
        return TotalMilestoneTiming10868(milestoneID: id, title: "\(row.title) · \(Words.timingSuffix)", lines: lines)
    }
}
