import Foundation

// MARK: - Tournament hub presentation (pure, testable)
//
// Every decision the hub screen makes about WHAT to show lives here as a value,
// so the contract can be asserted without rendering SwiftUI — the same seam
// `TournamentCardPresentation` opened for the Discover card.
//
// The rule this file exists to keep is D27: **a feed that returned nothing is
// labelled, not omitted.** A section that quietly disappears when its list is
// empty is indistinguishable, on the phone, from a section the app forgot to
// build — and today the US Open hub really does return an empty `bracket`, so
// that case is live, not hypothetical. Each section therefore resolves to
// either rows or a sentence, never to silence.

nonisolated struct TournamentHubPresentation: Equatable, Sendable {

    // MARK: Row values

    nonisolated struct SideRow: Equatable, Sendable, Identifiable {
        let id: String
        let name: String
        let flagUrl: String?
        /// Already formatted — "62%", "<1%", or the em-dash for no price.
        let percentText: String
        let hasPrice: Bool
        let isFavourite: Bool
    }

    nonisolated struct MatchRow: Equatable, Sendable, Identifiable {
        let id: String
        /// Non-nil only when this match resolves to an event page we can open.
        let eventId: Int?
        /// "Men's Singles · R64"
        let headline: String
        /// "4th Set" while live; "11:15 AM" or "Time TBD" before.
        let statusText: String
        let isLive: Bool
        let sides: [SideRow]
        /// Set when the match has no price at all, so the row says why the
        /// numbers are dashes instead of leaving the reader to guess.
        let noPriceNote: String?
    }

    nonisolated struct ResultRow: Equatable, Sendable, Identifiable {
        let id: String
        let eventId: Int?
        /// "Women's Singles · Round 2"
        let headline: String
        let winnerName: String
        let loserName: String
        /// "6-1, 6-4", or nil for a walkover with no scoreline.
        let score: String?
        /// "Retired" / "Walkover". Nil for an ordinary final — a retirement is
        /// not a scoreline and must not be printed as one.
        let completionNote: String?
    }

    nonisolated struct BoardRow: Equatable, Sendable, Identifiable {
        let id: String
        let rank: Int?
        let name: String
        let flagUrl: String?
        let percentText: String
        /// Movement in percentage POINTS over the tracked window, or nil when it
        /// is below a point and would round to a misleading "+0".
        let deltaPoints: Double?
    }

    nonisolated struct BoardSection: Equatable, Sendable, Identifiable {
        let id: String
        let title: String
        let rows: [BoardRow]
        /// "Top 6 of 36 still in the draw" — shown only when rows were trimmed.
        let trimNote: String?
        /// "Movement since 6 Aug." — what the `+33` beside a name measures
        /// (#3033), computed over the rows this card actually draws. `nil` when
        /// no drawn row carries a delta, because there is then nothing to
        /// reconcile and a sentence about an absent column is noise.
        let deltaWindowNote: String?
        /// The RACE chart above the rows (#2911). Always present, because a
        /// board that cannot be charted still says why in `emptyNote`.
        let chart: RaceChartData
    }

    /// One printed row of a curated question's field or comparison.
    nonisolated struct PropOutcomeRow: Equatable, Sendable, Identifiable {
        let id: String
        let name: String
        /// "45%" / "<1%". Nil when this subject has no number at all — a
        /// comparison keeps such a row deliberately, and it says so in words
        /// rather than printing a dash that reads as zero.
        let percentText: String?
        /// "No number yet" / "No number". Non-nil exactly when `percentText`
        /// is nil; the tense is the card's, not the row's.
        let missingText: String?
        /// A number that is not a current answer. Muted type, never the
        /// confident one — the card decides this once, for all of its rows.
        let isMuted: Bool
    }

    nonisolated struct PropRow: Equatable, Sendable, Identifiable {
        let id: String
        /// The question, as a person would ask it.
        let question: String
        /// One clause on why it is interesting, or nil.
        let hook: String?
        /// The big value on the right: the probability on an open answer card
        /// ("27%"), the RESULT in words on a settled one ("No"). Nil on a field
        /// or comparison card, which has no single answer to headline — picking
        /// the leader to fill the slot is precisely the guess the card refuses.
        let headline: String?
        /// A headline that is not a current answer — a stale reading, or a
        /// result. Never drawn in the confident type.
        let headlineIsMuted: Bool
        /// "Yes" / "Yes · Looks decided" — the name of the outcome the headline
        /// belongs to, under it. Nil on a settled or field card.
        let answerLine: String?
        /// "Settled 30 August 2026 · last reading 1%". Nil for an open question.
        let settledLine: String?
        /// "Last number 45 hours ago" / "No number yet". Nil on a live card, on
        /// an incomplete comparison (which says something truer below), and on a
        /// settled one: an age chip on a closed question answers "is this
        /// current?", which is no longer the reader's question.
        let freshnessNote: String?
        /// What a multi-market comparison is missing, named rather than hidden.
        let incompleteNote: String?
        /// The field / comparison rows. Empty on an answer card, whose one
        /// printed outcome is the headline.
        let outcomes: [PropOutcomeRow]
        let isLive: Bool
    }

    // MARK: Header

    let title: String
    let subtitle: String?

    // MARK: Sections — rows OR a sentence, never nothing

    let liveMatches: [MatchRow]
    let liveEmptyNote: String?

    let upcomingMatches: [MatchRow]
    let upcomingEmptyNote: String?

    let results: [ResultRow]
    let resultsEmptyNote: String?

    let boards: [BoardSection]
    let boardsEmptyNote: String?

    /// The curated questions (#3043). Same contract as every other section:
    /// rows OR a sentence.
    let props: [PropRow]
    let propsEmptyNote: String?
    /// "Showing 6 of 9 questions" — only when the register sent more than the
    /// phone prints.
    let propsTrimNote: String?

    /// Always present. The bracket is either absent from the feed or present and
    /// undrawn by this screen, and the reader is told which.
    let bracketNote: String

    /// "Match prices last updated 4 hours ago." Nil when the feed reported no
    /// observation age — which is itself different from "fresh", so nothing is
    /// claimed in that case.
    let priceAgeNote: String?

    /// Shown instead of the sections when the whole payload came back empty.
    let wholePayloadEmptyNote: String?

    // MARK: Bounds
    //
    // The response carries 40 slate matches, 256 results and 80 board rows. A
    // phone screen that renders all of them is a scroll nobody finishes, and it
    // is also the shape that made a tall `ImageRenderer` return nil PNG data.
    // These are the display bounds, stated once.

    static let upcomingLimit = 8
    static let resultsLimit = 10
    static let boardRowLimit = 6
    /// The register curates this list — five entries today — so the cap is a
    /// backstop against a register that grows, not the curation itself.
    static let propsLimit = 6
    /// How many rows a ranked FIELD question prints. A comparison prints all of
    /// its declared rows and is not subject to this.
    static let propFieldRankLimit = 3

    // MARK: - Build

    init(response: TournamentHubResponse) {
        title = response.title ?? "Tournament"
        subtitle = response.subtitle

        let byEspn = response.eventLinks?.byEspn ?? [:]
        let allMatches = response.slate?.matches ?? []

        func eventId(for match: TournamentHubMatch) -> Int? {
            if let direct = match.eventId { return direct }
            guard let espn = match.espnCompetitionId else { return nil }
            return byEspn[espn]
        }

        let live = allMatches
            .filter { $0.isLive }
            .sorted { ($0.scheduledDate ?? "") < ($1.scheduledDate ?? "") }
            .map { Self.matchRow($0, eventId: eventId(for: $0)) }

        let upcoming = allMatches
            .filter { !$0.isLive }
            .sorted { ($0.scheduledDate ?? "") < ($1.scheduledDate ?? "") }
            .prefix(Self.upcomingLimit)
            .map { Self.matchRow($0, eventId: eventId(for: $0)) }

        liveMatches = live
        liveEmptyNote = live.isEmpty ? "No match is being played right now." : nil

        upcomingMatches = Array(upcoming)
        upcomingEmptyNote = upcoming.isEmpty
            ? "Nothing else is scheduled in the order of play." : nil

        // Newest first. The feed serves results oldest-first, and a hub whose
        // "Latest results" opens on a qualifying match from nine days ago is
        // worse than useless — it reads as a dead page.
        let finished = (response.results?.matches ?? [])
            .sorted { ($0.completedAt ?? "") > ($1.completedAt ?? "") }
            .prefix(Self.resultsLimit)
            .compactMap { Self.resultRow($0, eventId: $0.espnCompetitionId.flatMap { byEspn[$0] }) }

        results = Array(finished)
        resultsEmptyNote = finished.isEmpty ? "No completed matches yet." : nil

        // The chart's two windows are facts about the TOURNAMENT, not about a
        // board, so they are read once here and handed to every board.
        let windowStarts = RaceChart.windowStarts(
            mainDrawStartsAt: response.mainDrawStartsAt,
            results: response.results?.matches ?? []
        )
        let boardSections = response.boards.compactMap { Self.boardSection($0, starts: windowStarts) }
        boards = boardSections
        boardsEmptyNote = boardSections.isEmpty
            ? "Nobody is priced to win the title yet." : nil

        let allProps = response.props
        let shownProps = allProps.prefix(Self.propsLimit).map { Self.propRow($0) }
        props = Array(shownProps)
        propsEmptyNote = shownProps.isEmpty
            ? "No curated questions on this tournament yet — they appear here as "
              + "Kalshi and Polymarket open them."
            : nil
        propsTrimNote = allProps.count > shownProps.count
            ? "Showing \(shownProps.count) of \(allProps.count) questions"
            : nil

        let bracketEntries = response.bracket.values.reduce(0) { $0 + $1.count }
        bracketNote = bracketEntries == 0
            ? "No bracket yet — the tournament feed returned an empty draw."
            : "The feed has a bracket; this screen doesn't draw it yet."

        priceAgeNote = Self.priceAgeNote(hours: response.slate?.ageHours)

        let nothingAtAll = live.isEmpty && upcoming.isEmpty
            && finished.isEmpty && boardSections.isEmpty && shownProps.isEmpty
        wholePayloadEmptyNote = nothingAtAll
            ? "The tournament feed returned nothing for this event." : nil
    }

    // MARK: - Row builders

    private static func matchRow(_ match: TournamentHubMatch, eventId: Int?) -> MatchRow {
        let priced = match.sides.contains { $0.probability != nil }
        let best = match.sides.compactMap(\.probability).max()

        // UX-P114 / #2279: a row printing two sides of ONE question decides both
        // percents together. Formatting each side on its own is the 101% those
        // fixed — the US Open served `0.845 / 0.155` on 2026-09-04, a complement
        // pair landing on `.5` for both sides at once, and this screen printed
        // 85% beside 16%. A draw with anything other than two sides is not a duel
        // and keeps rendering exactly as before.
        let duelPercents: [Int?] = match.sides.count == 2
            ? renderedDuelPercents(
                away: match.sides[0].probability,
                home: match.sides[1].probability
            )
            : []

        let sides = match.sides.enumerated().map { index, side in
            SideRow(
                id: side.id,
                name: side.displayName,
                flagUrl: side.image?.flagUrl,
                percentText: formatProbabilityOrDash(
                    side.probability,
                    renderedPercent: index < duelPercents.count ? duelPercents[index] : nil
                ),
                hasPrice: side.probability != nil,
                // A two-way match with both sides at the same price has no
                // favourite; marking both would be a claim the numbers do not
                // make.
                isFavourite: priced
                    && side.probability != nil
                    && side.probability == best
                    && match.sides.filter { $0.probability == best }.count == 1
            )
        }

        return MatchRow(
            id: match.id,
            eventId: eventId,
            headline: [match.drawLabel, match.round]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " · "),
            statusText: statusText(for: match),
            isLive: match.isLive,
            sides: sides,
            noPriceNote: priced ? nil : "No price on this match yet."
        )
    }

    private static func statusText(for match: TournamentHubMatch) -> String {
        if match.isLive {
            if let detail = match.statusDetail, !detail.isEmpty { return detail }
            return "Live"
        }
        if match.startIsTbd == true { return "Time TBD" }
        guard let iso = match.scheduledDate, let date = isoDate(iso) else { return "Time TBD" }
        return startTimeFormatter.string(from: date)
    }

    private static func resultRow(_ result: TournamentHubResult, eventId: Int?) -> ResultRow? {
        guard result.players.count == 2 else { return nil }
        let winner = result.players.first { $0.isWinner == true }
            ?? result.players.first { $0.entityKey == result.winnerEntityKey }
        guard let winner else { return nil }
        guard let loser = result.players.first(where: { $0.entityKey != winner.entityKey }) else {
            return nil
        }

        let completion = (result.completion ?? "final").lowercased()
        let note: String?
        switch completion {
        case "retired": note = "Retired"
        case "walkover": note = "Walkover"
        case "final": note = nil
        default: note = completion.capitalized
        }

        let score = (result.score?.isEmpty == false) ? result.score : nil

        return ResultRow(
            id: result.id,
            eventId: eventId,
            headline: [result.drawLabel, result.round]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " · "),
            winnerName: winner.displayName,
            loserName: loser.displayName,
            score: score,
            completionNote: note
        )
    }

    private static func boardSection(
        _ board: TournamentHubBoard,
        starts: RaceChartWindowStarts
    ) -> BoardSection? {
        // Someone knocked out is not a contender; the board keeps them so the
        // web page can grey them, but a six-row phone list must spend its rows
        // on players still in the draw.
        let standing = board.rows.filter { ($0.state ?? "live") == "live" }
        guard !standing.isEmpty else { return nil }

        let ordered = standing.sorted { lhs, rhs in
            switch (lhs.rank, rhs.rank) {
            case let (l?, r?): return l < r
            case (nil, _?): return false
            case (_?, nil): return true
            default: return (lhs.probability ?? 0) > (rhs.probability ?? 0)
            }
        }
        let shown = ordered.prefix(boardRowLimit)

        return BoardSection(
            id: board.id,
            title: board.label ?? board.draw,
            rows: shown.map { row in
                BoardRow(
                    id: row.id,
                    rank: row.rank,
                    name: row.displayName,
                    flagUrl: row.image?.flagUrl,
                    percentText: formatProbabilityOrDash(row.probability),
                    deltaPoints: movementPoints(row.trendDelta)
                )
            },
            trimNote: ordered.count > shown.count
                ? "Top \(shown.count) of \(ordered.count) still in the draw"
                : nil,
            // Over `shown`, not `ordered`: the note reconciles the deltas a
            // reader can see with the chart above them, and the rows below the
            // cut are not on this screen to be reconciled.
            deltaWindowNote: RaceChart.deltaWindowNote(rows: Array(shown)),
            chart: raceChart(ordered, starts: starts)
        )
    }

    /// The board's top three as a RACE chart (#2911).
    ///
    /// Built from the SAME ordered rows the list below it draws, so the chart
    /// and the list can never describe two different fields — and the legend
    /// names the three, which is how a reader of a six-row list knows which
    /// three have lines.
    private static func raceChart(
        _ ordered: [TournamentHubBoardRow],
        starts: RaceChartWindowStarts
    ) -> RaceChartData {
        let series = RaceChart.series(from: ordered)
        let ranges = RaceChart.availableRanges(starts: starts)
        let drawable = ranges.filter { RaceChart.isDrawable(series, range: $0, starts: starts) }

        // The two reasons a board has no chart are different facts and get
        // different sentences. "Nobody is priced" is a market state; "one
        // reading" is a history state, and a reader told the wrong one will go
        // looking for the wrong thing.
        let note: String?
        if series.isEmpty {
            note = "No contender on this board has a price to chart."
        } else if drawable.isEmpty {
            note = "Only one reading so far — there is no line to draw yet."
        } else {
            note = nil
        }

        return RaceChartData(
            series: series,
            ranges: ranges,
            initialRange: RaceChart.defaultRange(series: series, starts: starts),
            starts: starts,
            emptyNote: note
        )
    }

    // MARK: - The curated questions (#3043)
    //
    // ═══ WHY THESE RULES ARE RE-STATED AND NOT APPROXIMATED ═══
    //
    // The web's pure layer for this section is `frontend/lib/tournamentProps.ts`,
    // and almost every rule in it is a scar. Which outcomes a card PRINTS and
    // whether it is allowed the confident treatment are the two decisions that
    // produced CERT-411 (a field card took its liveness from the leader alone,
    // so a three-week-old runner-up rendered as current), CERT-430 (a two-market
    // comparison with one leg unpriced laundered the leg that arrived into a
    // one-player answer to a two-player question) and UX-P207 (a settled
    // question printing a still-quoted 1% as the live answer).
    //
    // A phone that eyeballs the same payload and reaches its own conclusion is a
    // SECOND IMPLEMENTATION of that contract, not a port of it, and it would
    // re-earn those three defects one at a time. So the rules below are the same
    // rules in the same order, each naming the web function it mirrors, and the
    // guards in `TournamentHubPropsTests` pin the specimens that produced them.

    /// Declared markets behind this card. Absent reads as one — treating an old
    /// capture as an ordinary card is the safe direction. (`propLegs`)
    static func propLegs(_ prop: TournamentHubProp) -> Int {
        guard let legs = prop.legs, legs > 0 else { return 1 }
        return legs
    }

    /// Several declared markets, one question. (`propIsComparison`)
    static func propIsComparison(_ prop: TournamentHubProp) -> Bool { propLegs(prop) > 1 }

    /// The outcome the register says answers the title. (`answerOutcome`)
    ///
    /// Curated, never inferred: the headline is the ANSWER, not the biggest
    /// number in the market, because "Will Sinner actually play?" resolves on a
    /// Yes priced at 1% while a No sits at 99%.
    static func propAnswerOutcome(_ prop: TournamentHubProp) -> TournamentHubPropOutcome? {
        guard let key = prop.answerEntityKey else { return nil }
        return prop.outcomes.first { $0.entityKey == key }
    }

    /// The outcomes a card actually PRINTS — the only ones that get a vote on
    /// its freshness. (`printedOutcomes`)
    ///
    /// An answer card prints one. A COMPARISON prints every declared subject,
    /// unpriced ones included and with no rank limit — both halves of that are
    /// CERT-430's fix, since a comparison the reader can only partly see is not
    /// the object the card claims to be, whether the missing subject was dropped
    /// for having no price or for sorting fourth. A field card ranks its top few.
    static func propPrintedOutcomes(_ prop: TournamentHubProp) -> [TournamentHubPropOutcome] {
        if let answer = propAnswerOutcome(prop) { return [answer] }
        if propIsComparison(prop) {
            // Best first, unquoted subjects last — they are what the card is
            // about to admit to, and burying them mid-list hides the admission.
            return prop.outcomes.sorted { lhs, rhs in
                switch (lhs.probability, rhs.probability) {
                case let (l?, r?): return l > r
                case (nil, _?): return false
                case (_?, nil): return true
                default: return false
                }
            }
        }
        return prop.outcomes
            .filter { $0.probability != nil }
            .sorted { ($0.probability ?? 0) > ($1.probability ?? 0) }
            .prefix(propFieldRankLimit)
            .map { $0 }
    }

    /// What a comparison is missing, or nil when it is whole.
    /// (`propIncompleteComparison`)
    ///
    /// `undeclared` counts legs the payload promised and delivered no row for at
    /// all — our fault rather than the market's, told in the same breath because
    /// from where the reader sits it is the same hole.
    static func propIncompleteComparison(
        _ prop: TournamentHubProp
    ) -> (subjects: [TournamentHubPropOutcome], undeclared: Int)? {
        guard propIsComparison(prop) else { return nil }
        let subjects = prop.outcomes.filter { $0.probability == nil }
        let undeclared = max(0, propLegs(prop) - prop.outcomes.count)
        if subjects.isEmpty && undeclared == 0 { return nil }
        return (subjects, undeclared)
    }

    /// The register's settlement verdict, or nil for an open question.
    /// (`propSettlement`)
    ///
    /// `settled != true` is nil — an explicit `true`, not truthiness. A payload
    /// that grows `settled: "yes"` one day renders OPEN and trips a guard,
    /// rather than quietly switching every card on the page into the settled
    /// treatment. Knowing a question has closed needs the schedule and the
    /// results; that is the register's job and this file never forms the verdict.
    static func propSettlement(_ prop: TournamentHubProp) -> (answer: String?, at: String?)? {
        guard prop.settled == true else { return nil }
        let answer = (prop.settledAnswer ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return (answer.isEmpty ? nil : answer, prop.settledAt)
    }

    /// Is this card allowed the confident treatment? (`propIsPresentedAsLive`)
    ///
    /// ANY printed contributor that is not live demotes the whole card — a card
    /// is as fresh as its oldest printed number, the same rule the boards and the
    /// slate keep. A settled question is never live however recently it was
    /// quoted (a live QUOTE on a closed question is not a live ANSWER), and an
    /// incomplete comparison is never live whatever it prints.
    static func propIsLive(_ prop: TournamentHubProp) -> Bool {
        guard propSettlement(prop) == nil else { return false }
        guard propIncompleteComparison(prop) == nil else { return false }
        let printed = propPrintedOutcomes(prop)
        guard !printed.isEmpty else { return false }
        return printed.allSatisfy { $0.probability != nil && $0.probabilityIsLive == true }
    }

    /// Longest age among the printed outcomes — the card is as fresh as its
    /// oldest. (`propGoverningAgeHours`)
    ///
    /// Nil when ANY printed outcome has no age, because a reading that never
    /// arrived is older than every reading that did (gotcha #53).
    static func propGoverningAgeHours(_ prop: TournamentHubProp) -> Double? {
        let printed = propPrintedOutcomes(prop)
        guard !printed.isEmpty else { return nil }
        let ages = printed.compactMap { $0.ageHours }.filter { $0.isFinite }
        guard ages.count == printed.count else { return nil }
        return ages.max()
    }

    /// "32 min ago" / "32 hours ago" / "20 days ago" / "never".
    /// (`freshnessAge`)
    ///
    /// Rounded DOWN, like every other age the product prints: "8 days ago" must
    /// never flatter to "7".
    static func propFreshnessAge(_ hours: Double?) -> String {
        guard let hours, hours.isFinite else { return "never" }
        if hours < 1 { return "\(max(1, Int(hours * 60))) min ago" }
        if hours < 48 {
            let whole = Int(hours)
            return "\(whole) hour\(whole == 1 ? "" : "s") ago"
        }
        return "\(Int(hours / 24)) days ago"
    }

    /// The settled date, pinned to UTC and to English. (`PropSettlement.at`)
    ///
    /// Deliberately NOT the device's calendar: `2026-08-30T15:05:00+00:00` is
    /// the 29th in Honolulu, and a settled date that moves by where the reader
    /// is standing is a different fact per phone. The app prints English
    /// everywhere else on this screen, so the formatter is pinned too — which is
    /// also what lets a guard assert the string instead of re-deriving it
    /// (gotcha #44).
    static func propSettledDate(_ iso: String?) -> String? {
        guard let iso, let date = isoDate(iso) else { return nil }
        return settledDateFormatter.string(from: date)
    }

    private static func propRow(_ prop: TournamentHubProp) -> PropRow {
        let settlement = propSettlement(prop)
        let incomplete = propIncompleteComparison(prop)
        let printed = propPrintedOutcomes(prop)
        let answer = propAnswerOutcome(prop)
        let isLive = propIsLive(prop)

        // The headline. On an open question it is the probability; on a settled
        // one it is the RESULT, in the same slot and the same weight, because
        // that is the answer to the question printed beside it. A register that
        // knows a card closed but not how it came out prints nothing here rather
        // than a number — the settled line below says so instead.
        let headline: String?
        if let settlement {
            headline = settlement.answer
        } else if let answer, let probability = answer.probability {
            headline = formatProbability(probability)
        } else {
            headline = nil
        }

        // A field or comparison card's rows. An answer card's single printed
        // outcome IS the headline and is not repeated as a row.
        let rows: [TournamentHubPropOutcome] = answer == nil ? printed : []
        let outcomes = rows.map { outcome in
            PropOutcomeRow(
                id: outcome.entityKey,
                name: outcome.displayName,
                percentText: outcome.probability.map { formatProbability($0) },
                // Tense: an open comparison may still be completed, a closed one
                // may not, and "yet" on a settled card promises a later that
                // will not come.
                missingText: outcome.probability == nil
                    ? (settlement == nil ? "No number yet" : "No number")
                    : nil,
                isMuted: !isLive
            )
        }

        // The answer card's muted second line. `looksDecided` is inferred from
        // the number sitting at a rail — a resolved market trades at 0 or 1 —
        // and is a weaker statement than the register's verdict, so it is only
        // ever said on a card the register has NOT settled.
        var answerLine: String?
        if settlement == nil, let answer {
            let decided = !printed.isEmpty && printed.allSatisfy {
                guard let p = $0.probability else { return false }
                return p <= 0.001 || p >= 0.999
            }
            answerLine = decided ? "\(answer.displayName) · Looks decided" : answer.displayName
        }

        // "Settled 30 August 2026 · last reading 1%". The last reading is KEPT
        // and demoted: deleting it throws away a true fact (the market really
        // did close at 1%), and headlining it makes a finished question look
        // open. Counted, never assumed — a comparison retains subjects it has no
        // number for, so "there are rows" and "there are readings" are different
        // questions and only the second may be claimed here.
        var settledLine: String?
        if let settlement {
            var parts = ["Settled"]
            if let date = propSettledDate(settlement.at) { parts[0] = "Settled \(date)" }
            if let answer, let probability = answer.probability {
                parts.append("last reading \(formatProbability(probability))")
            } else {
                let readings = rows.filter { $0.probability != nil }.count
                if readings > 0 { parts.append(readings == 1 ? "last reading" : "last readings") }
            }
            if settlement.answer == nil { parts.append("result not published") }
            settledLine = parts.joined(separator: " · ")
        }

        // An incomplete comparison gets the sentence instead of the age: both are
        // the card admitting something, and "Last number 20 hours ago" beside a
        // row that has never had a number at all is the less true of the two.
        var freshnessNote: String?
        if !isLive && settlement == nil && incomplete == nil {
            let age = propGoverningAgeHours(prop)
            let label = age == nil ? "No number yet" : "Last number \(propFreshnessAge(age))"
            // Name the old ones when only SOME are old: a row built from a
            // one-hour reading and a twenty-day one is muted, and the bare age
            // would claim we had not looked at any of it in three weeks.
            let stale = printed.filter { $0.probability != nil && $0.probabilityIsLive != true }
            freshnessNote = (stale.isEmpty || stale.count == printed.count)
                ? label
                : "\(stale.map(\.displayName).joined(separator: " + ")): \(label)"
        }

        var incompleteNote: String?
        if let incomplete {
            // Name the SUBJECT, not the market: "no number for Carlos Alcaraz"
            // is a fact the reader can hold, "leg KXGRANDSLAM-CALC26 is
            // unpriced" is one of ours. And speak only about what we HAVE —
            // `observed_at` can be populated beside a null probability, so
            // "never reached us" is contradicted by a timestamp on the same row.
            let named = incomplete.subjects.map(\.displayName).filter { !$0.isEmpty }
            let unnamed = incomplete.undeclared
            let who: String
            if named.isEmpty {
                who = unnamed == 1 ? "one of the names in it" : "\(unnamed) of the names in it"
            } else {
                who = nameList(named) + (unnamed > 0 ? " and \(unnamed) more" : "")
            }
            incompleteNote = settlement == nil
                ? "We have no number for \(who) yet, so this comparison is not complete."
                : "We have no number for \(who), so this comparison is not complete and "
                    + "the question has closed."
        }

        return PropRow(
            id: prop.key,
            question: prop.title,
            hook: (prop.hook?.isEmpty == false) ? prop.hook : nil,
            headline: headline,
            headlineIsMuted: !isLive,
            answerLine: answerLine,
            settledLine: settledLine,
            freshnessNote: freshnessNote,
            incompleteNote: incompleteNote,
            outcomes: outcomes,
            isLive: isLive
        )
    }

    /// "Alcaraz", "Alcaraz and Sinner", "A, B and C".
    private static func nameList(_ names: [String]) -> String {
        guard names.count > 1 else { return names.first ?? "" }
        return names.dropLast().joined(separator: ", ") + " and " + (names.last ?? "")
    }

    /// Percentage points, suppressed below one point.
    ///
    /// "+0" reads as a measured non-move rather than as noise, so a sub-point
    /// change is dropped instead of rounded. The Discover feed's cards apply the
    /// same rule to their own payload; the two are deliberately not sharing one
    /// helper, because gotcha #129 cuts both ways — a rule two endpoints happen
    /// to agree on today is a coincidence, not a contract, and coupling them
    /// means a change to one silently rewrites the other.
    private static func movementPoints(_ fraction: Double?) -> Double? {
        guard let fraction else { return nil }
        let points = fraction * 100
        return abs(points) >= 1 ? points : nil
    }

    /// The feed's own observation age, rendered as a sentence.
    ///
    /// Deliberately reads the server's `age_hours` rather than differencing a
    /// timestamp against the device clock: the number is then the same one the
    /// server measured, and the test that pins this copy does not branch on
    /// what time it runs (gotcha #44).
    static func priceAgeNote(hours: Double?) -> String? {
        guard let hours, hours >= 0 else { return nil }
        if hours < 1 / 60.0 { return "Match prices updated just now." }
        if hours < 1 {
            let minutes = max(Int((hours * 60).rounded()), 1)
            return "Match prices last updated \(minutes) minute\(minutes == 1 ? "" : "s") ago."
        }
        let whole = Int(hours.rounded())
        return "Match prices last updated \(whole) hour\(whole == 1 ? "" : "s") ago."
    }
}

// MARK: - Date helpers

private let isoWithFraction: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

private let isoPlain: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

/// The hub serves both `2026-09-03T18:25:00+00:00` and
/// `2026-09-03T19:50:02.857675+00:00`; one formatter parses one of them.
private func isoDate(_ value: String) -> Date? {
    isoWithFraction.date(from: value) ?? isoPlain.date(from: value)
}

/// "30 August 2026", in UTC and in English — see `propSettledDate`.
private let settledDateFormatter: DateFormatter = {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(identifier: "UTC")
    f.dateFormat = "d MMMM yyyy"
    return f
}()

private let startTimeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateStyle = .none
    f.timeStyle = .short
    return f
}()
