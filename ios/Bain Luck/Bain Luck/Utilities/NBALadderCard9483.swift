import Foundation

/// #9483 — the NBA page's game-story cards in the app (design freeze v328,
/// `nfl-web-nba-adoption-v328/NBA-MAPPING.md`; the web twin is
/// `frontend/lib/nbaEventCards.ts`). Two ladders join the projected finish
/// the NFL deck already draws:
///
/// - **Scoring expectations**: one dot per full-game total line ("Over 206.5"),
///   with the actual total on the same points axis;
/// - **Winning margin**: one dot per team "wins by over N" line on ONE signed
///   axis — home lines right of the tie, away lines left — never a complement
///   of the other side.
///
/// READ FROM THE SERVED QUESTION MATRIX (`game_question_matrix`, contract
/// `10238.v1`). The producer's typing is the authority: only typed,
/// full-game, own-side options are drawn, and nothing is reclassified here.
/// Every other original stays in the catalog.
///
/// WHICH NUMBER A DOT IS (Root's selected fallback, 10/15):
/// - before tip-off: the option's published value, only while `quoted` and its
///   clock is recent — that price IS the pregame chance;
/// - once play starts: the producer's admitted pregame pin
///   (`comparison.state == comparable`, `baseline.basis == pregame_pin`,
///   dated), never a live or settled price;
/// - after the final the comparison serves no pin on a settled option
///   (`not_quoted`); the option's own `pregame_reading` (#11125) may carry it.
///   Without either the card says the pregame chance is unavailable rather
///   than reading 0/100 or rebuilding it from movement.
/// Results are the producer's `result.state`, shown only on a finished page.
nonisolated enum NBAEventCards9483 {
    static let sportKey = "basketball_nba"
    static let matrixContract = "10238.v1"
    /// A ladder needs this many lines to be a shape rather than a list.
    static let minimumLadderLines = 3

    static func applies(sportKey: String?) -> Bool {
        sportKey == Self.sportKey
    }
}

nonisolated struct NBALadderCard9483: Equatable, Identifiable {
    nonisolated enum Family: String, Equatable { case total, margin }
    nonisolated enum Phase: Equatable { case before, during, after }
    nonisolated enum Side: Equatable { case game, home, away }

    /// The exact original behind a dot, frozen with the card so Details show
    /// what was on screen until Refresh — each number named for what it is.
    nonisolated struct Detail: Equatable {
        let label: String
        let marketName: String
        let source: String?
        /// The published value, only while `quoted`.
        let quoted: Double?
        let observedAt: String?
        /// The admitted pregame pin, or nil.
        let baseline: Double?
        let baselineObservedAt: String?
        let result: Bool?
    }

    nonisolated struct Point: Equatable, Identifiable {
        /// `o:` + contributor outcome ids — the producer's own identity.
        let optionKey: String
        /// Total: the line. Margin: the home side's margin (home wins by over
        /// N → +N, away → −N).
        let x: Double
        /// "Over 206.5", "Clippers by 4+".
        let label: String
        let side: Side
        /// The chance this card draws (see the type note), or nil.
        let chance: Double?
        /// During play only: the current quote beside the drawn pregame pin.
        let now: Double?
        /// The quote's clock, so a current number can expire while a reader
        /// is looking (`current(at:)`).
        let observedAt: String?
        /// The producer's verdict, finished pages only.
        let result: Bool?
        let detail: Detail
        var id: String { optionKey }
    }

    /// What the page knows when it builds the ladders.
    nonisolated struct Input {
        let matrix: EventQuestionMatrix?
        let status: String?
        let commenceTime: Date?
        /// Nil wherever the page does not print a score (before play).
        let homeScore: Int?
        let awayScore: Int?
        /// The projected finish's pregame pair, when the page draws one.
        let pregameProjection: (home: Double, away: Double)?
        let homeShort: String
        let awayShort: String
        let now: Date
    }

    let family: Family
    let phase: Phase
    let points: [Point]
    /// Total (home + away) or home margin (home − away) from the page's
    /// score; nil before play.
    let actual: Double?
    /// The pregame projection on the same axis, or nil.
    let forecast: Double?
    let awayShort: String
    let homeShort: String

    var id: String { family.rawValue }

    var title: String { family == .total ? "Scoring expectations" : "Winning margin" }

    /// What the card calls the drawn number, by phase.
    var caption: String {
        let what = family == .total ? "finishing above each line" : "winning by more than each margin"
        if phase == .before { return "Pregame chance of \(what)" }
        if points.contains(where: { $0.chance != nil }) { return "Chance before tip-off of \(what)" }
        return "Pregame chance unavailable for these lines"
    }

    /// The default point: the drawn line nearest even odds, ties low; with
    /// none drawn, the line nearest the actual; else the middle line.
    var defaultIndex: Int? {
        var best: (index: Int, distance: Double)?
        for (index, point) in points.enumerated() {
            guard let chance = point.chance else { continue }
            let distance = abs(chance - 0.5)
            if best == nil || distance < best!.distance { best = (index, distance) }
        }
        if let best { return best.index }
        guard !points.isEmpty else { return nil }
        if let actual {
            var near = 0
            for (index, point) in points.enumerated() where abs(point.x - actual) < abs(points[near].x - actual) {
                near = index
            }
            return near
        }
        return points.count / 2
    }

    /// A value on this card's axis in words: "205" for a total, "Clippers by
    /// 3" / "Warriors by 2.7" / "Tie" for a margin.
    func words(_ value: Double) -> String {
        guard family == .margin else { return Self.number(value) }
        if value == 0 { return "Tie" }
        return "\(value > 0 ? homeShort : awayShort) by \(Self.number(abs(value)))"
    }

    /// A whole number stays whole; a projection keeps one decimal.
    static func number(_ value: Double) -> String {
        value.rounded() == value ? String(Int(value)) : String(format: "%.1f", value)
    }

    /// The card as it may be shown at `now`: a current quote that has stopped
    /// being observed loses its number — before tip-off the dot, during play
    /// the "now" beside the pin — so a card held open never keeps a price
    /// current because someone was reading it. A pin is historical and does
    /// not age.
    func current(at now: Date) -> NBALadderCard9483 {
        guard phase != .after else { return self }
        var changed = false
        let aged = points.map { point -> Point in
            let ages = phase == .before ? point.chance != nil : point.now != nil
            guard ages, !NFLMilestoneCard9483.isRecent(point.observedAt, now: now) else { return point }
            changed = true
            return Point(optionKey: point.optionKey, x: point.x, label: point.label, side: point.side,
                         chance: phase == .before ? nil : point.chance, now: nil,
                         observedAt: point.observedAt, result: point.result, detail: point.detail)
        }
        guard changed else { return self }
        return NBALadderCard9483(family: family, phase: phase, points: aged, actual: actual,
                                 forecast: forecast, awayShort: awayShort, homeShort: homeShort)
    }

    // MARK: - Building

    /// The full-game total-points ladder, or nil with fewer than three typed lines.
    @MainActor
    static func total(_ input: Input) -> NBALadderCard9483? {
        let phase = Self.phase(input)
        var points: [Point] = []
        for question in questions(input.matrix) {
            guard question.kind == QuestionMatrixKind.countThreshold.rawValue,
                  question.quantity?.key == "points", question.subject?.side == "game",
                  question.period?.key == "full_game", question.predicate?.relation == "ge",
                  let line = question.predicate?.line ?? question.predicate?.bound.map({ $0 - 0.5 }),
                  line.isFinite else { continue }
            let own = question.options.filter { $0.side == "over" }
            guard own.count == 1, let option = own.first else { continue }
            points.append(point(question, option, x: line, label: "Over \(number(line))",
                                side: .game, phase: phase, input: input))
        }
        return ladder(.total, phase, points, input) { $0.home + $0.away }
    }

    /// The full-game "wins by over N" ladder on one signed axis: each team's
    /// own lines in its own colour, never a complement of the other side.
    @MainActor
    static func margin(_ input: Input) -> NBALadderCard9483? {
        let phase = Self.phase(input)
        var points: [Point] = []
        for question in questions(input.matrix) {
            guard question.kind == QuestionMatrixKind.signedHandicap.rawValue,
                  question.quantity?.key == "points", question.period?.key == "full_game",
                  question.predicate?.relation == "handicap",
                  let line = question.predicate?.line, line.isFinite, line < 0 else { continue }
            let side: Side
            switch question.subject?.side {
            case "home"?: side = .home
            case "away"?: side = .away
            default: continue
            }
            let own = question.options.filter { $0.side == question.subject?.side }
            guard own.count == 1, let option = own.first else { continue }
            let by = -line
            let team = side == .home ? input.homeShort : input.awayShort
            points.append(point(question, option, x: side == .home ? by : -by,
                                label: "\(team) by \(Int(by.rounded(.down)) + 1)+",
                                side: side, phase: phase, input: input))
        }
        return ladder(.margin, phase, points, input) { $0.home - $0.away }
    }

    /// The typed questions of a game matrix this build reads, or none.
    private static func questions(_ matrix: EventQuestionMatrix?) -> [QuestionMatrixQuestion] {
        guard let matrix, matrix.contract == NBAEventCards9483.matrixContract,
              matrix.displayScope == nil || matrix.displayScope == QuestionMatrixScope.game.rawValue
        else { return [] }
        return matrix.questions.filter { $0.typing?.state == "typed" }
    }

    @MainActor
    private static func phase(_ input: Input) -> Phase {
        if EventState.isFinished(input.status) { return .after }
        // `suspended` is NOT proof the game began (#4021, `EventState`): a game
        // suspended before its tip-off keeps its pregame quotes, so the clock
        // decides. A suspended game past tip-off is `.during` with no "now"
        // (see `point`), the NFL milestone rule.
        if input.status == "live"
            || EventState.hasStarted(commenceTime: input.commenceTime, now: input.now) {
            return .during
        }
        return .before
    }

    /// The producer's admitted pregame pin, or nil: the quoted comparison's
    /// baseline, else the option's own `pregame_reading` (#11125), which a
    /// settled option still carries. The reading must name this option's one
    /// contributor — a pin for another outcome is never borrowed — and an
    /// exact 0 or 1 is a settlement value, not a chance. Also the final MLB
    /// stories' pin rule (#11284), so the two pages cannot read one differently.
    static func pin(_ option: QuestionMatrixOption) -> (probability: Double, at: String)? {
        if let comparison = option.comparison, comparison.state == "comparable",
           let baseline = comparison.baseline, baseline.basis == "pregame_pin",
           let probability = baseline.probability, probability.isFinite, (0...1).contains(probability),
           let at = baseline.observedAt, !at.isEmpty {
            return (probability, at)
        }
        guard let reading = option.pregameReading, reading.state == "available",
              reading.basis == "pregame_pin",
              let outcome = reading.outcomeId, option.contributorOutcomeIds == [outcome],
              let probability = reading.probability, probability.isFinite, probability > 0, probability < 1,
              let at = reading.observedAt, !at.isEmpty else { return nil }
        return (probability, at)
    }

    @MainActor
    private static func point(
        _ question: QuestionMatrixQuestion, _ option: QuestionMatrixOption,
        x: Double, label: String, side: Side, phase: Phase, input: Input
    ) -> Point {
        let quoted = option.published.quotedValue
        let observedAt = option.published.observedAt
        let recent = quoted != nil && NFLMilestoneCard9483.isRecent(observedAt, now: input.now)
        let pin = Self.pin(option)
        let chance: Double?
        let now: Double?
        switch phase {
        case .before:
            chance = recent ? quoted : nil
            now = nil
        case .during:
            chance = pin?.probability
            // A suspended game has no current price to set beside the pin.
            now = recent
                && !EventState.isSuspendedAndStarted(input.status, commenceTime: input.commenceTime, now: input.now)
                ? quoted : nil
        case .after:
            chance = pin?.probability
            now = nil
        }
        return Point(
            optionKey: option.optionKey, x: x, label: label, side: side,
            chance: chance, now: now, observedAt: observedAt,
            result: phase == .after ? option.result?.isWinner : nil,
            detail: Detail(
                label: option.label.isEmpty ? question.label : option.label,
                marketName: question.marketName ?? question.label,
                source: option.published.source, quoted: quoted, observedAt: observedAt,
                baseline: pin?.probability, baselineObservedAt: pin?.at,
                result: option.result?.isWinner))
    }

    @MainActor
    private static func ladder(
        _ family: Family, _ phase: Phase, _ points: [Point], _ input: Input,
        quantity: ((home: Double, away: Double)) -> Double
    ) -> NBALadderCard9483? {
        // Two options on one line on one axis would be two prices for one
        // dot: the line is refused, never resolved by order.
        var counts: [Double: Int] = [:]
        for point in points { counts[point.x, default: 0] += 1 }
        let kept = points.filter { counts[$0.x] == 1 }.sorted { $0.x < $1.x }
        guard kept.count >= NBAEventCards9483.minimumLadderLines else { return nil }
        let score: (home: Double, away: Double)? = phase == .before ? nil
            : input.homeScore.flatMap { home in input.awayScore.map { (Double(home), Double($0)) } }
        return NBALadderCard9483(
            family: family, phase: phase, points: kept,
            actual: score.map(quantity),
            forecast: input.pregameProjection.map { (quantity($0) * 10).rounded() / 10 },
            awayShort: input.awayShort, homeShort: input.homeShort)
    }
}
