import Foundation

/// #11284 — the final MLB page's game stories (Atlas MLB final reader;
/// design ref #10868: the v471 MLB route with the v472 native baseball
/// composition, handoff `mlb-final-production-handoff-20261019`).
///
/// After an MLB game the page keeps the approved probability-first headline
/// and paired journey (#9483), and under it deals five story slots — home
/// runs, strikeouts, run totals, extra innings, the associated series — that
/// open full size in the existing reader (`NFLCardReader9483`).
///
/// EVERY NUMBER IS ONE AN EXISTING DELIVERY ALREADY SERVES, NAMED FOR WHAT IT
/// IS. The v472 reference is a captured fixture; nothing here reads its
/// players, order, percentages, clocks or grades. In particular:
/// - a saved pregame chance is the typed `after_player_props` expectation
///   (10237.v1) or a prop row's served pregame mark, never a terminal quote;
/// - a player's final count is the typed official final only (10237.v1 types
///   hits and home runs). A legacy `actual`/`hit` or a box score never becomes
///   one, so a strikeout ladder says its final result is unavailable;
/// - a venue's settlement is the venue's (`OutcomeVerdict`, the producer's
///   `result.state`) and stays apart from any sporting comparison;
/// - no in-game prop history is delivered, so a recorded in-game probability
///   is "Not captured", never borrowed from a neighbour or interpolated;
/// - a quote the catalog withholds after the final (`QuestionCatalog9483
///   .reading` → `.settled`) is withheld in Details too, and an exact 0 or 1
///   or an undated value never prints as a chance.
///
/// A slot with no associated original deals no card; a slot whose comparison
/// cannot be built keeps its card with the unavailable parts said, and every
/// original stays reachable in All markets. The order is fixed per final
/// (no ranking service), so a card never moves while someone reads it.
enum MLBFinalPage11284 {
    static let sportKey = "baseball_mlb"

    /// A finished MLB game, by its status — never by its date. Upcoming and
    /// live MLB, and every other sport, keep their existing pages.
    static func applies(sportKey: String?, status: String?) -> Bool {
        sportKey == Self.sportKey && EventState.isFinished(status)
    }

    /// Where the approved paired headline and journey (#9483) draw: the NFL
    /// and NBA pages as before, plus the final MLB page. `NFLRecognizablePage9483
    /// .applies` itself is unchanged, so no NFL-only projection, milestone or
    /// pregame/live arm reaches baseball.
    static func adoptsPairedPage(sportKey: String?, status: String?) -> Bool {
        NFLRecognizablePage9483.applies(sportKey: sportKey) || applies(sportKey: sportKey, status: status)
    }
}

/// The five story slots, in the captured final's order.
enum MLBStoryFamily11284: String, CaseIterable {
    case homeRuns, strikeouts, totals, extraInnings, series
}

// MARK: - Exact originals

/// A venue's settlement of one original, in words that claim no more than the
/// payload proves. Pending is only a row nothing has graded; a grade this page
/// cannot prove — a served loss on a market it cannot see resolved, a producer
/// `unknown` or `void`, a retraction — is Not confirmed, never Lost.
enum MLBVenueResult11284: Hashable {
    case won, lost, open, pending, notConfirmed

    var label: String {
        switch self {
        case .won: return "Won"
        case .lost: return "Lost"
        case .open: return "Open"
        case .pending: return "Pending"
        case .notConfirmed: return "Not confirmed"
        }
    }

    /// A served row's own grade. The market's status is not served beside
    /// the row, so `OutcomeVerdict` is asked as for an open market: only a
    /// venue's authoritative WON crosses it (#6082), and a served false — the
    /// column's default — cannot be told from no grade. So there is no Lost
    /// here: a row with any grade that is not a provable win is Not confirmed.
    static func venue(isWinner: Bool?, resolutionSource: String?) -> Self {
        if isWinner == nil && resolutionSource == nil { return .pending }
        return OutcomeVerdict.verdict(isWinner: isWinner, resolutionSource: resolutionSource,
                                      marketResolved: false) == .won ? .won : .notConfirmed
    }

    /// The producer's verdict for a typed option (`result.state`): won, lost
    /// and open verbatim, no result ungraded, and `unknown`, `void` or any
    /// unread state Not confirmed.
    static func producer(_ result: QuestionMatrixResult?) -> Self {
        switch result?.state {
        case nil: return .pending
        case "won"?: return .won
        case "lost"?: return .lost
        case "open"?: return .open
        default: return .notConfirmed
        }
    }
}

/// The exact original behind a story's line, frozen inside the card so its
/// Details show what was on screen until Refresh. Every value is named for
/// what it is — saved chance, last recorded quote, final count, venue
/// result — and none is merged into another.
struct MLBOriginal11284: Equatable, Identifiable {
    struct Field: Equatable {
        let label: String
        let value: String
    }

    struct Section: Equatable {
        let title: String?
        let fields: [Field]
    }

    let id: String
    let title: String
    let sections: [Section]

    static func stamp(_ iso: String?) -> String {
        SourceAge.preciseStamp(iso) ?? "time unavailable"
    }

    static func chance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    /// A chance strictly between 0 and 1: an exact 0 or 1 is a settlement
    /// value, not a chance (`NBALadderCard9483.pin`).
    static func openChance(_ value: Double?) -> Double? {
        guard let value = chance(value), value > 0, value < 1 else { return nil }
        return value
    }

    /// A recorded value Details may print: an open chance with a time the
    /// reader can read. Undated, terminal or unreadable values print nothing.
    static func recorded(_ value: Double?, at iso: String?) -> String? {
        guard let value = openChance(value), let stamp = SourceAge.preciseStamp(iso) else { return nil }
        return "\(formatProbability(value)) · \(stamp)"
    }

    static func idList(_ ids: [Int]?) -> String? {
        guard let ids, !ids.isEmpty else { return nil }
        return ids.map(String.init).joined(separator: ", ")
    }

    /// A served prop row: its own side, line, venue, the pregame mark on the
    /// Over axis it is served on, the venue's result and its identities. A
    /// legacy `actual`/`hit` is not printed: it is not an official final. Nor
    /// is the row's last quote: this page exists only after the final, where
    /// the catalog withholds it (`QuestionCatalog9483.reading` → `.settled`),
    /// and here it is an after-final refresh, not an in-game observation.
    static func propFields(_ prop: GameMarketPlayerProp) -> [Field] {
        var fields = [Field(label: "Original side", value: prop.outcomeName)]
        if let threshold = prop.threshold, threshold.isFinite {
            fields.append(Field(label: "Line", value: NBALadderCard9483.number(threshold)))
        }
        if let venue = SourceLabels.label(for: prop.source) {
            fields.append(Field(label: "Venue", value: venue))
        }
        fields.append(Field(label: "Pregame mark · Over",
                            value: openChance(prop.pregameMark).map { formatProbability($0) } ?? "Unavailable"))
        fields.append(Field(label: "Venue result",
                            value: MLBVenueResult11284.venue(isWinner: prop.isWinner,
                                                             resolutionSource: prop.resolutionSource).label))
        if let market = prop._marketId { fields.append(Field(label: "Market", value: String(market))) }
        if let outcomes = idList(prop.contributorOutcomeIds) {
            fields.append(Field(label: "Outcome", value: outcomes))
        }
        return fields
    }

    /// A typed option of the game or series matrix (10238.v1). A source's raw
    /// leg prints only beside a `quoted` published value — never as the quote
    /// of a settled option (`QuestionMatrixSourceEvidence`) — and only when it
    /// is dated and not terminal.
    ///
    /// `pinLabel` is display only: the words beside the producer's pin. The
    /// pin, its value, its stamp and every other field are the same whatever
    /// it says. Every existing caller keeps the default; #10868's run
    /// milestones name it apart from the chance their card shows.
    static func option(_ question: QuestionMatrixQuestion, _ option: QuestionMatrixOption,
                       pin: (probability: Double, at: String)?, eventID: Int,
                       pinLabel: String = "Pregame chance") -> MLBOriginal11284 {
        var fields = [Field(label: "Original side", value: option.label.isEmpty ? question.label : option.label)]
        if let venue = SourceLabels.label(for: option.published.source) {
            fields.append(Field(label: "Venue", value: venue))
        }
        fields.append(Field(label: pinLabel,
                            value: pin.map { "\(formatProbability($0.probability)) · \(stamp($0.at))" } ?? "Unavailable"))
        for evidence in option.published.quotedValue == nil ? [] : option.sourceEvidence ?? [] {
            guard let value = recorded(evidence.rawProbability, at: evidence.observedAt) else { continue }
            let venue = SourceLabels.label(for: evidence.source) ?? "Venue"
            fields.append(Field(label: "Last recorded · \(venue)", value: value))
        }
        fields.append(Field(label: "Venue result", value: MLBVenueResult11284.producer(option.result).label))
        if let markets = idList(option.marketIds) { fields.append(Field(label: "Market", value: markets)) }
        if let outcomes = idList(option.contributorOutcomeIds) {
            fields.append(Field(label: "Outcome", value: outcomes))
        }
        return MLBOriginal11284(
            id: "mlb-o:\(eventID):q:\(question.questionKey)|\(option.optionKey)",
            title: question.marketName ?? question.label,
            sections: [Section(title: nil, fields: fields),
                       Section(title: nil, fields: [Field(
                           label: "Note", value: "Recorded values are history, not a current chance.")])])
    }

    /// A served `other` row. Its last quote is withheld after the final, as
    /// the catalog withholds it.
    static func other(_ row: GameMarketOther, eventID: Int) -> MLBOriginal11284 {
        var fields = [Field(label: "Original side", value: row.outcomeName)]
        if let venue = SourceLabels.label(for: row.source) {
            fields.append(Field(label: "Venue", value: venue))
        }
        fields.append(Field(label: "Pregame chance", value: "Unavailable"))
        fields.append(Field(label: "Venue result",
                            value: MLBVenueResult11284.venue(isWinner: row.isWinner,
                                                             resolutionSource: row.resolutionSource).label))
        if let market = row._marketId { fields.append(Field(label: "Market", value: String(market))) }
        if let outcomes = idList(row.contributorOutcomeIds) {
            fields.append(Field(label: "Outcome", value: outcomes))
        }
        return MLBOriginal11284(id: "mlb-o:\(eventID):other:\(row.id)|\(idList(row.contributorOutcomeIds) ?? "")",
                                title: row.marketName, sections: [Section(title: nil, fields: fields)])
    }
}

// MARK: - The deck

/// What the page knows when it deals the final MLB stories.
struct MLBFinalDeckInput11284 {
    let eventID: Int
    let sportKey: String?
    let status: String?
    let homeTeam: String
    let awayTeam: String
    /// Nil wherever the page does not print a score.
    let homeScore: Int?
    let awayScore: Int?
    let gameMarkets: GameMarketsResponse?
    let relatedFutures: RelatedFuturesResponse?
}

enum MLBFinalCard11284: Equatable, Identifiable {
    case homeRuns(MLBHomeRunCard11284)
    case strikeouts(MLBMilestoneCard11284)
    case totals(MLBTotalsCard11284)
    case extraInnings(MLBExtraInningsCard11284)
    case series(MLBSeriesCard11284)

    var family: MLBStoryFamily11284 {
        switch self {
        case .homeRuns: return .homeRuns
        case .strikeouts: return .strikeouts
        case .totals: return .totals
        case .extraInnings: return .extraInnings
        case .series: return .series
        }
    }

    var id: String { "mlb:\(family.rawValue)" }

    var title: String {
        switch self {
        case .homeRuns: return "Home runs"
        case .strikeouts(let card): return "\(card.player) · \(card.stat)"
        case .totals: return "Run totals"
        case .extraInnings: return "Extra innings"
        case .series: return "The series"
        }
    }

    /// Every original this card holds, for its Details.
    var originals: [MLBOriginal11284] {
        switch self {
        case .homeRuns(let card): return card.entries.map(\.original)
        case .strikeouts(let card): return card.targets.map(\.original)
        case .totals(let card): return card.lines.map(\.original)
        case .extraInnings(let card): return card.outcomes.map(\.original)
        case .series(let card): return card.questions.flatMap(\.options).map(\.original)
        }
    }
}

enum MLBFinalDeck11284 {
    /// The final MLB stories, in the captured final's order, each slot from
    /// its own delivery of THIS event only. Empty off the final MLB page.
    static func cards(_ input: MLBFinalDeckInput11284) -> [MLBFinalCard11284] {
        guard MLBFinalPage11284.applies(sportKey: input.sportKey, status: input.status) else { return [] }
        let markets = input.gameMarkets.flatMap { $0.eventId == input.eventID ? $0 : nil }
        let series = input.relatedFutures.flatMap { $0.eventId == input.eventID ? $0.seriesQuestionMatrix : nil }
        let teams = [input.homeTeam, input.awayTeam]
        let total = input.homeScore.flatMap { home in input.awayScore.map { home + $0 } }
        let slots: [MLBFinalCard11284?] = [
            MLBHomeRunCard11284.build(markets, eventID: input.eventID).map { .homeRuns($0) },
            MLBMilestoneCard11284.build(markets, teams: teams, eventID: input.eventID).map { .strikeouts($0) },
            MLBTotalsCard11284.build(markets?.gameQuestionMatrix, actualTotal: total,
                                     eventID: input.eventID).map { .totals($0) },
            MLBExtraInningsCard11284.build(markets?.other ?? [], eventID: input.eventID).map { .extraInnings($0) },
            MLBSeriesCard11284.build(series, eventID: input.eventID).map { .series($0) },
        ]
        return slots.compactMap { $0 }
    }

    /// The original a Details request names, from the cards the reader holds
    /// — never the live payload — or nil when no held card carries it.
    static func original(_ id: String, in cards: [NFLEventCard9483]) -> MLBOriginal11284? {
        for card in cards {
            guard case .mlb(let mlb) = card, let original = mlb.originals.first(where: { $0.id == id }) else { continue }
            return original
        }
        return nil
    }
}

// MARK: - Home runs

/// Players' saved pregame chances of a home run beside their official final
/// counts, all on one probability scale.
struct MLBHomeRunCard11284: Equatable {
    enum Story: Equatable {
        /// Official finals exist and someone homered: the lowest saved
        /// chances among those who did.
        case homered
        /// No official home run to show: the highest saved chances, each
        /// with its final count or "unavailable".
        case likeliest
    }

    struct Entry: Equatable, Identifiable {
        let questionKey: String
        let player: String
        /// The typed saved pregame chance (`savedProbability`).
        let saved: Double
        /// The typed official final count; nil is unavailable, never 0.
        let finalCount: Int?
        let side: PlayerPropsTeam.Side
        let original: MLBOriginal11284
        var id: String { questionKey }
    }

    static let maximumEntries = 3

    let eventID: Int
    let story: Story
    let entries: [Entry]

    var headline: String {
        story == .homered ? "Who homered, against their pregame chances" : "The likeliest home-run hitters"
    }

    /// Why these players, in the evidence's own terms.
    var reason: String {
        switch story {
        case .homered: return "Lowest pregame chances among players with an official home run"
        case .likeliest:
            return entries.contains { $0.finalCount != nil }
                ? "Highest pregame chances of a home run"
                : "Highest pregame chances of a home run · official finals unavailable"
        }
    }

    /// One shared scale: 0–25% when every chance fits, else the next 5%
    /// above the largest — a chance is never clipped to the illustration.
    var scaleCeiling: Double {
        let top = entries.map(\.saved).max() ?? 0
        return min(1, max(0.25, (top * 20).rounded(.up) / 20))
    }

    /// The typed home-run questions (1+, over, full game) with a saved
    /// chance, after the After grid's own admission (`drawable`).
    static func build(_ markets: GameMarketsResponse?, eventID: Int) -> MLBHomeRunCard11284? {
        guard let after = AfterPropsMatrixLayout.drawable(markets?.afterPlayerProps) else { return nil }
        let props = markets?.playerProps ?? []
        let entries: [Entry] = after.questions.compactMap { question in
            guard question.statKey == "home_runs", question.periodKey == "full_game",
                  question.predicate.isAtLeast, question.predicate.count == 1, question.predicate.side == "over",
                  question.subject.kind != "team",
                  let saved = question.expectation.savedProbability else { return nil }
            let actual = after.actual(for: question)
            return Entry(questionKey: question.questionKey, player: question.subject.label, saved: saved,
                         finalCount: actual?.finalCount,
                         side: side(of: question, in: props),
                         original: original(question, actual: actual, stat: after.stat(question.statKey),
                                            eventID: eventID))
        }
        guard !entries.isEmpty else { return nil }
        let homered = entries.filter { ($0.finalCount ?? 0) >= 1 }
            .sorted { $0.saved != $1.saved ? $0.saved < $1.saved : $0.questionKey < $1.questionKey }
        if !homered.isEmpty {
            return MLBHomeRunCard11284(eventID: eventID, story: .homered,
                                       entries: Array(homered.prefix(maximumEntries)))
        }
        let likeliest = entries
            .sorted { $0.saved != $1.saved ? $0.saved > $1.saved : $0.questionKey < $1.questionKey }
        return MLBHomeRunCard11284(eventID: eventID, story: .likeliest,
                                   entries: Array(likeliest.prefix(maximumEntries)))
    }

    /// The player's team side from a served prop row that is one of the
    /// question's own contributors — identity, never a name.
    static func side(of question: AfterPropQuestion, in props: [GameMarketPlayerProp]) -> PlayerPropsTeam.Side {
        let ids = Set(question.contributorOutcomeIds ?? [])
        guard !ids.isEmpty else { return .unknown }
        let team = props.first { !ids.isDisjoint(with: $0.contributorOutcomeIds ?? []) }?.playerTeam
        return PlayerPropsTeam.side(for: team)
    }

    static func original(_ question: AfterPropQuestion, actual: AfterPropActual?, stat: AfterPropStat?,
                         eventID: Int) -> MLBOriginal11284 {
        typealias Field = MLBOriginal11284.Field
        let unit = stat?.unitPlural ?? "home runs"
        var saved: [Field] = [Field(
            label: "Saved pregame chance",
            value: question.expectation.savedProbability.map { formatProbability($0) } ?? "Unavailable")]
        if question.expectation.savedProbability != nil {
            saved.append(Field(label: "Saved", value: MLBOriginal11284.stamp(question.expectation.observedAt)))
        }
        for contributor in question.expectation.contributors {
            let venue = SourceLabels.label(for: contributor.source) ?? "Venue"
            saved.append(Field(label: "\(venue) · \(contributor.outcomeName ?? "outcome")",
                               value: MLBOriginal11284.recorded(contributor.probability, at: contributor.observedAt)
                                   ?? "Unavailable"))
        }
        let finalValue: String
        if let count = actual?.finalCount {
            finalValue = "\(count) \(count == 1 ? (stat?.unitSingular ?? "home run") : unit)"
        } else {
            finalValue = actual?.state == "pending" ? "Pending" : "Unavailable"
        }
        var result: [Field] = [Field(label: "Official final", value: finalValue)]
        if let label = actual?.sourceLabel, actual?.finalCount != nil {
            result.append(Field(label: "Final source", value: label))
        }
        let comparison: String
        switch question.comparison?.state {
        case "reached"?: comparison = "Reached \(question.predicate.label)"
        case "below"?: comparison = "Below \(question.predicate.label)"
        default: comparison = "Unavailable"
        }
        result.append(Field(label: "Against \(question.predicate.label)", value: comparison))
        result.append(Field(label: "Venue settlement",
                            value: MLBVenueResult11284.venue(isWinner: question.venueGrade?.isWinner,
                                                             resolutionSource: question.venueGrade?.resolutionSource).label))
        var ids: [Field] = []
        if let markets = MLBOriginal11284.idList(question._marketIds) { ids.append(Field(label: "Market", value: markets)) }
        if let outcomes = MLBOriginal11284.idList(question.contributorOutcomeIds) {
            ids.append(Field(label: "Outcome", value: outcomes))
        }
        return MLBOriginal11284(
            id: "mlb-o:\(eventID):after:\(question.questionKey)",
            title: "\(question.subject.label) · \(question.predicate.label) \(unit)",
            sections: [MLBOriginal11284.Section(title: "Before first pitch", fields: saved),
                       MLBOriginal11284.Section(title: "After the final", fields: result),
                       MLBOriginal11284.Section(title: nil, fields: ids)])
    }
}

// MARK: - Strikeout milestones

/// Sporting performance against a selected count — never a venue's grade.
/// Port of v472 `BaseballMilestoneContext.result`: a missing, negative,
/// fractional or non-finite input is "Final result unavailable", so a missing
/// count never reads as zero.
nonisolated enum MLBMilestoneResult11284 {
    static func result(actual: Double?, milestone: Double?) -> String {
        guard let actual, let milestone, actual.isFinite, milestone.isFinite,
              actual >= 0, milestone >= 0, actual.rounded() == actual, milestone.rounded() == milestone
        else { return "Final result unavailable" }
        let difference = actual - milestone
        if difference == 0 { return "Reached the milestone" }
        let amount = String(format: "%.0f", locale: Locale(identifier: "en_US_POSIX"), abs(difference))
        return difference > 0 ? "Finished \(amount) above" : "Finished \(amount) short"
    }
}

/// One player's strikeout ladder as milestones: the saved pregame chance of
/// reaching each count, a selected target, and the official final when one
/// is typed.
struct MLBMilestoneCard11284: Equatable {
    struct Target: Equatable, Identifiable {
        /// The Over row (`GameMarketPlayerProp.id`) — the target's identity.
        let rowID: String
        let threshold: Double
        /// "7+": at least this many.
        let milestone: Int
        /// The Over row's served pregame mark, or nil.
        let pregame: Double?
        /// Both original sides of this line, exactly as served.
        let original: MLBOriginal11284
        var id: String { rowID }
    }

    let eventID: Int
    let player: String
    /// The venue's stat words, verbatim ("Strikeouts").
    let stat: String
    let source: String?
    let side: PlayerPropsTeam.Side
    let targets: [Target]
    /// The typed official final, joined by contributor identity; nil in
    /// 10237.v1, which does not type strikeouts.
    let finalCount: Int?

    var unit: String { stat.lowercased() }

    /// The target the card opens on: the priced line nearest even odds.
    var defaultIndex: Int? { PlayerPropsFamily.defaultTarget(probabilities: targets.map(\.pregame)) }

    var reason: String { "Highest pregame strikeout expectation on this game" }

    /// `count ≥ N` for an "N+" row; `count > X.5` is `≥ floor(X.5) + 1`.
    static func milestone(_ threshold: Double) -> Int {
        threshold.rounded() == threshold ? Int(threshold) : Int(threshold.rounded(.down)) + 1
    }

    /// The candidate ladders: every served strikeout ladder, one per player,
    /// stat and venue (venues are never blended), with three or more priced
    /// distinct lines (`PlayerMilestoneProfile`'s flat-ladder refusal). The
    /// card shows the one the venues expected the most strikeouts from — the
    /// highest line nearest even odds — then the longer priced ladder, then
    /// the key, so a relaunch deals the same card.
    static func build(_ markets: GameMarketsResponse?, teams: [String], eventID: Int) -> MLBMilestoneCard11284? {
        let props = markets?.playerProps ?? []
        var ladders: [String: (player: String, stat: String, source: String?, rows: [GameMarketPlayerProp])] = [:]
        for prop in props {
            guard let shape = ladderShape(prop), shape.stat.lowercased().contains("strikeout"),
                  !PlayerPropsFamily.isTeamSubject(shape.player, teams: teams) else { continue }
            // The venue is the ladder's identity only (never printed from
            // here; the card keeps `prop.source` itself): a row with no served
            // venue groups under an empty venue segment, never a named one.
            let venueSegment = prop.source.map { "|\($0)" } ?? "|"
            let key = "\(shape.player)|\(shape.stat)\(venueSegment)"
            ladders[key, default: (shape.player, shape.stat, prop.source, [])].rows.append(prop)
        }
        let after = AfterPropsMatrixLayout.drawable(markets?.afterPlayerProps)
        let candidates: [(key: String, card: MLBMilestoneCard11284)] = ladders.compactMap { key, ladder in
            let overs = ladder.rows.filter {
                $0.threshold?.isFinite == true && QuestionCatalog9483.lineSide(QuestionCatalog9483.row($0)) == .over
            }
            // Two Over rows on one line would be two chances for one target:
            // the line is refused, never resolved by order.
            var counts: [Double: Int] = [:]
            for row in overs { counts[row.threshold!, default: 0] += 1 }
            let kept = overs.filter { counts[$0.threshold!] == 1 }
            let finalCount = typedFinal(overs: kept, after: after)
            let unit = ladder.stat.lowercased()
            let targets: [Target] = kept.map { over in
                let threshold = over.threshold!
                let under = ladder.rows.first {
                    $0.threshold == threshold && $0._marketId == over._marketId
                        && QuestionCatalog9483.lineSide(QuestionCatalog9483.row($0)) == .under
                }
                var pregame = MLBOriginal11284.chance(over.pregameMark)
                if let p = pregame, !(p > 0 && p < 1) { pregame = nil }
                let target = milestone(threshold)
                var sections = [MLBOriginal11284.Section(title: "Over · \(over.marketName)",
                                                         fields: MLBOriginal11284.propFields(over))]
                if let under {
                    sections.append(MLBOriginal11284.Section(title: "Under · \(under.marketName)",
                                                             fields: MLBOriginal11284.propFields(under)))
                }
                // The final count is not the count at any quote's time, and
                // no in-game observation of this line is delivered.
                sections.append(MLBOriginal11284.Section(title: "\(target)+ \(unit)", fields: [
                    .init(label: "Official final", value: finalCount.map { "\($0) \(unit)" } ?? "Unavailable"),
                    .init(label: "Against \(target)+",
                          value: MLBMilestoneResult11284.result(actual: finalCount.map(Double.init),
                                                                milestone: Double(target))),
                    .init(label: "Recorded in game", value: "Not captured"),
                    .init(label: "Count at quote time", value: "Unavailable"),
                ]))
                return Target(rowID: over.id, threshold: threshold, milestone: target, pregame: pregame,
                              original: MLBOriginal11284(id: "mlb-o:\(eventID):target:\(over.id)",
                                                         title: "\(ladder.player) · \(target)+ \(unit)",
                                                         sections: sections))
            }.sorted { $0.threshold < $1.threshold }
            guard PlayerMilestoneProfile.profile(thresholds: targets.map(\.threshold),
                                                 probabilities: targets.map(\.pregame)) != nil else { return nil }
            let card = MLBMilestoneCard11284(
                eventID: eventID, player: ladder.player, stat: ladder.stat, source: ladder.source,
                side: PlayerPropsTeam.side(for: ladder.rows.compactMap(\.playerTeam).first),
                targets: targets, finalCount: finalCount)
            return (key, card)
        }
        return candidates.sorted { a, b in
            let (la, lb) = (a.card.defaultIndex.map { a.card.targets[$0].threshold } ?? -.infinity,
                            b.card.defaultIndex.map { b.card.targets[$0].threshold } ?? -.infinity)
            if la != lb { return la > lb }
            let (pa, pb) = (a.card.targets.filter { $0.pregame != nil }.count,
                            b.card.targets.filter { $0.pregame != nil }.count)
            if pa != pb { return pa > pb }
            return a.key < b.key
        }.first?.card
    }

    /// The player and stat words of a served ladder row, in either venue
    /// spelling: Kalshi's `"<matchup>: Strikeouts"` with outcome
    /// `"<Player>: 7+"`, or `"<Player>: Strikeouts O/U 6.5"` with outcome
    /// `Over`/`Under`. Nil for anything else.
    static func ladderShape(_ prop: GameMarketPlayerProp) -> (player: String, stat: String)? {
        let outcome = prop.outcomeName.split(separator: ":", maxSplits: 1)
        let market = prop.marketName.split(separator: ":", maxSplits: 1)
        if outcome.count == 2, market.count == 2 {
            let player = PropSubject.display(outcome[0].trimmingCharacters(in: .whitespaces))
            let stat = market[1].trimmingCharacters(in: .whitespaces)
            return player.isEmpty || stat.isEmpty ? nil : (player, stat)
        }
        guard outcome.count == 1, market.count == 2 else { return nil }
        let player = PropSubject.display(market[0].trimmingCharacters(in: .whitespaces))
        let stat = PlayerPropsFamily.name(statLabel: String(market[1]))
        return player.isEmpty || stat.isEmpty ? nil : (player, stat)
    }

    /// The official final for this ladder: the typed After actual of the
    /// questions whose contributors ARE this ladder's rows. Every matched
    /// question must name the same actual; anything else is unavailable.
    static func typedFinal(overs: [GameMarketPlayerProp], after: AfterPlayerProps?) -> Int? {
        guard let after else { return nil }
        let ids = Set(overs.flatMap { $0.contributorOutcomeIds ?? [] })
        guard !ids.isEmpty else { return nil }
        let questions = after.questions.filter { !ids.isDisjoint(with: $0.contributorOutcomeIds ?? []) }
        let actuals = Set(questions.compactMap { after.actual(for: $0)?.actualKey })
        guard actuals.count == 1, let question = questions.first else { return nil }
        return after.actual(for: question)?.finalCount
    }
}

// MARK: - Run totals

/// Every typed full-game run line, the venue's result on each, and the
/// final total summed from the page's own final score.
struct MLBTotalsCard11284: Equatable {
    struct Line: Equatable, Identifiable {
        /// `o:` + contributor outcome ids — the producer's identity.
        let optionKey: String
        let line: Double
        let label: String
        /// The producer's admitted pregame pin, or nil.
        let pregame: Double?
        /// The producer's verdict (`result.state`), its unknown kept apart
        /// from open.
        let venueResult: MLBVenueResult11284
        let original: MLBOriginal11284
        var id: String { optionKey }
    }

    let eventID: Int
    let lines: [Line]
    /// Home + away from the final score; nil without one. Never a quote.
    let actualTotal: Int?

    var reason: String { "Every full-game run line, with the venue's result" }

    /// The line the card opens on: the highest line the final total cleared,
    /// else the lowest line, else nil.
    var defaultIndex: Int? {
        guard !lines.isEmpty else { return nil }
        if let actualTotal, let index = lines.lastIndex(where: { $0.line < Double(actualTotal) }) { return index }
        return 0
    }

    /// The sporting comparison of the final total with a line — the score
    /// against the number, never the venue's grade.
    func comparison(_ line: Line) -> String? {
        guard let actualTotal else { return nil }
        let total = Double(actualTotal)
        if total == line.line { return "Final \(actualTotal) runs · on the line" }
        return "Final \(actualTotal) runs · \(total > line.line ? "above" : "below") this line"
    }

    /// `pinLabel` reaches each line original's pin field only (`MLBOriginal11284
    /// .option`); the lines, their order, pins, results and identities do not
    /// depend on it. The final deck keeps the default.
    static func build(_ matrix: EventQuestionMatrix?, actualTotal: Int?, eventID: Int,
                      pinLabel: String = "Pregame chance") -> MLBTotalsCard11284? {
        guard let matrix, matrix.contract == NBAEventCards9483.matrixContract,
              matrix.displayScope == nil || matrix.displayScope == QuestionMatrixScope.game.rawValue
        else { return nil }
        var lines: [Line] = []
        for question in matrix.questions where question.typing?.state == "typed" {
            guard question.kind == QuestionMatrixKind.countThreshold.rawValue,
                  question.quantity?.key == "runs", question.subject?.side == "game",
                  question.period?.key == "full_game", question.predicate?.relation == "ge",
                  let line = question.predicate?.line ?? question.predicate?.bound.map({ $0 - 0.5 }),
                  line.isFinite else { continue }
            let own = question.options.filter { $0.side == "over" }
            guard own.count == 1, let option = own.first else { continue }
            let pin = NBALadderCard9483.pin(option)
            lines.append(Line(optionKey: option.optionKey, line: line,
                              label: "Over \(NBALadderCard9483.number(line)) runs",
                              pregame: pin?.probability, venueResult: .producer(option.result),
                              original: MLBOriginal11284.option(question, option, pin: pin, eventID: eventID,
                                                                pinLabel: pinLabel)))
        }
        var counts: [Double: Int] = [:]
        for line in lines { counts[line.line, default: 0] += 1 }
        let kept = lines.filter { counts[$0.line] == 1 }.sorted { $0.line < $1.line }
        guard kept.count >= NBAEventCards9483.minimumLadderLines else { return nil }
        return MLBTotalsCard11284(eventID: eventID, lines: kept, actualTotal: actualTotal)
    }
}

// MARK: - Extra innings

/// A venue's extra-innings market for this game, when one is served: each
/// side's venue result, never inferred from the final score.
struct MLBExtraInningsCard11284: Equatable {
    struct Outcome: Equatable, Identifiable {
        let label: String
        let venue: String?
        /// The venue's own settlement of the row.
        let venueResult: MLBVenueResult11284
        let original: MLBOriginal11284
        var id: String { original.id }
    }

    let eventID: Int
    let outcomes: [Outcome]

    /// Rows of this event's `other` markets whose market names the
    /// extra-innings question ("<matchup>: Extra Innings"). The rows are
    /// already this event's; the name only files them under this story.
    static func isExtraInnings(_ row: GameMarketOther) -> Bool {
        let stat = row.marketName.split(separator: ":").last.map {
            $0.trimmingCharacters(in: .whitespaces).lowercased()
        }
        return stat == "extra innings"
    }

    static func build(_ rows: [GameMarketOther], eventID: Int) -> MLBExtraInningsCard11284? {
        let outcomes = rows.filter { isExtraInnings($0) }.map { row in
            Outcome(label: row.outcomeName, venue: SourceLabels.label(for: row.source),
                    venueResult: .venue(isWinner: row.isWinner, resolutionSource: row.resolutionSource),
                    original: MLBOriginal11284.other(row, eventID: eventID))
        }
        return outcomes.isEmpty ? nil : MLBExtraInningsCard11284(eventID: eventID, outcomes: outcomes)
    }
}

// MARK: - The series

/// The associated series' own typed questions (10238.v1, series scope):
/// separate from this game, settled only by the producer, never by this
/// game's final.
struct MLBSeriesCard11284: Equatable {
    struct Option: Equatable, Identifiable {
        let optionKey: String
        let label: String
        /// The producer's admitted pregame pin, or nil.
        let pregame: Double?
        let result: MLBVenueResult11284
        let original: MLBOriginal11284
        var id: String { optionKey }
    }

    struct Question: Equatable, Identifiable {
        let questionKey: String
        let label: String
        let options: [Option]
        var id: String { questionKey }
    }

    let eventID: Int
    let questions: [Question]

    var optionCount: Int { questions.reduce(0) { $0 + $1.options.count } }

    var reason: String { "Separate series markets" }

    static func build(_ matrix: EventQuestionMatrix?, eventID: Int) -> MLBSeriesCard11284? {
        guard let matrix, matrix.contract == NBAEventCards9483.matrixContract,
              matrix.displayScope == QuestionMatrixScope.series.rawValue else { return nil }
        let questions: [Question] = matrix.questions.compactMap { question in
            guard question.typing?.state == "typed", !question.options.isEmpty else { return nil }
            let options = question.options.map { option in
                let pin = NBALadderCard9483.pin(option)
                return Option(optionKey: option.optionKey,
                              label: option.label.isEmpty ? question.label : option.label,
                              pregame: pin?.probability,
                              result: .producer(option.result),
                              original: MLBOriginal11284.option(question, option, pin: pin, eventID: eventID))
            }
            return Question(questionKey: question.questionKey, label: question.label, options: options)
        }
        return questions.isEmpty ? nil : MLBSeriesCard11284(eventID: eventID, questions: questions)
    }
}
