import SwiftUI

/// #9483 — **one inspected match-history moment, read at a useful size.**
///
/// The chart's game card (`GamePlayCardView`) prints both sides' chances in a
/// caption-sized run that shrinks at accessibility sizes and, off the
/// fullscreen chart, gives its row to a scoring play's description. That is
/// right for a tooltip riding a scrubbing finger, and wrong for a reader who
/// has deliberately held a moment to read it. This is the expanded reading of
/// that same moment: both named competitors' chances first and equally large,
/// the score beside them with its OWN observation time, then the game state
/// and any scoring play, each in words.
///
/// ═══ IT TRANSFORMS NOTHING ═══
///
/// The input is the `GamePlayPoint` the owner already resolved with
/// `OddsChartView.playPoint(for:sportKey:context:)` — the sole transformation
/// — plus the owner's names, colours and `gameFinished`. This file chooses no
/// source, takes no complement, resolves no phase, picks no selected-or-last
/// point and applies no age threshold. Nil is "Recorded moment unavailable",
/// never the latest point or a neighbour.
///
/// - Chances are `GamePlayCardView.printedLabels` unchanged: the duel rule,
///   the live `<1%` / `>99%` guard and the finished `0%` / `100%` result. An
///   absent away price reads "Unavailable" for that named side.
/// - The heading is the point's supplied `phase`: Pregame win chance, Final
///   chart reading, else Recorded win chance. `gameFinished` alone never makes
///   an inspected point final, and nothing here says Current or Live.
/// - The probability's time is `SourceAge.preciseStamp(point.timestamp)`.
/// - A carried score is labelled an earlier update and dated by its own
///   `scoreObservedAt` through `GamePlayPoint.asOfText`, never by the
///   probability's time. Period/clock keep `badgeDisplay` and
///   `stateAsOfDisplay` verbatim.
/// - A pregame point hides the carried score, play and state-as-of; the
///   Pregame badge stays. That reads the explicit phase; it infers no cutoff.
///
/// SCOPE: paired sports only — two named competitors. It cannot show a
/// soccer draw (a draw-priced point arrives with no away price, and the away
/// side reads Unavailable) or a golf field. Tennis's dedicated reader and
/// soccer's three-way chart are separate components and are untouched.
///
/// ═══ MOUNTING BOUNDARY ═══
///
/// This view grows to fit its content. It must NOT replace the floating scrub
/// tooltip or the fixed header above the live plot, where a change in height
/// moves the plot under the scrubbing finger (#925's fixed two-line box). A
/// later mount belongs in an existing expanded, scrollable or held-inspection
/// region, or in proven stable geometry. It owns no scroll container, control,
/// state, timer or navigation.
enum ExpandedRecordedMatchMoment9483 {
    static let unavailableTitle = "Recorded moment unavailable"
    static let chanceLabel = "Win chance"
    static let scoreLabel = "Score"
    static let scoreUnavailable = "Score unavailable"

    /// One named competitor at the inspected moment.
    struct Side: Equatable {
        static let unavailable = "Unavailable"

        let name: String
        /// The shared printed label ("62%", ">99%"); nil when this side has no price.
        let chance: String?
        /// Drawn only from a complete pair after pregame; a genuine 0 stays 0.
        let score: Int?

        var chanceText: String { chance ?? Self.unavailable }
    }

    enum Score: Equatable {
        /// Pregame: carried game facts are not shown.
        case hidden
        /// After pregame with no complete pair. Never filled with 0.
        case unavailable
        /// Both sides' scores sit on `Side.score`; `note` dates the score itself.
        case pair(note: String?)
    }

    struct Play: Equatable {
        let type: String?
        let text: String?
    }

    struct Content: Equatable {
        let heading: String
        /// The probability's own time; nil when the timestamp does not parse.
        let stamp: String?
        let home: Side
        let away: Side
        let score: Score
        /// `point.badgeDisplay`, verbatim; nil when it prints nothing.
        let badge: String?
        /// `point.stateAsOfDisplay`, verbatim, beside the badge it dates.
        let stateAsOf: String?
        let play: Play?
        let spoken: String

        var recordedLine: String { stamp.map { "Recorded \($0)" } ?? "Time unknown" }
    }

    static func heading(_ phase: ChartReadoutPhase9483?) -> String {
        switch phase {
        case .pregame?: return "Pregame win chance"
        case .final?: return "Final chart reading"
        case nil: return "Recorded win chance"
        }
    }

    /// The score's own date. A carried score says it is from an earlier update
    /// and names that update's time, or "time unknown" without one — the
    /// probability's time is never lent to it. An exact score with a date may
    /// name it; without one there is nothing to add.
    static func scoreNote(_ point: GamePlayPoint) -> String? {
        let observed = point.scoreObservedAt.map {
            GamePlayPoint.asOfText($0, pointDate: point.timestamp.asDate)
        }
        if point.scoreApprox {
            return "Score from an earlier update, " + (observed.map { "as of \($0)" } ?? "time unknown")
        }
        return observed.map { "Score as of \($0)" }
    }

    /// The play as the card reads it: its type, and its description, else its
    /// short text. Nothing supplied ⇒ no play; no prose is invented.
    static func play(_ play: ScoringPlay?) -> Play? {
        guard let play else { return nil }
        let type = play.type.flatMap { $0.isEmpty ? nil : $0 }
        let text = (play.description ?? play.shortText).flatMap { $0.isEmpty ? nil : $0 }
        guard type != nil || text != nil else { return nil }
        return Play(type: type, text: text)
    }

    static func content(point: GamePlayPoint?, homeName: String, awayName: String,
                        gameFinished: Bool) -> Content? {
        guard let point else { return nil }
        let printed = GamePlayCardView.printedLabels(home: point.homeProb, away: point.awayProb,
                                                     gameFinished: gameFinished)
        let pregame = point.phase == .pregame
        let drawsScore = !pregame && point.hasScore
        let home = Side(name: homeName, chance: printed.home,
                        score: drawsScore ? point.homeScore : nil)
        let away = Side(name: awayName, chance: printed.away,
                        score: drawsScore ? point.awayScore : nil)
        let score: Score = pregame ? .hidden
            : point.hasScore ? .pair(note: scoreNote(point)) : .unavailable
        let badge = point.badgeDisplay.isEmpty ? nil : point.badgeDisplay
        // With no badge, `stateAsOfDisplay` can only be dating a carried score
        // — the same `asOfText` the score note already prints — so it is not
        // printed twice. Pregame hides it with the rest of the carried state.
        let stateAsOf = pregame || badge == nil ? nil : point.stateAsOfDisplay
        let title = Self.heading(point.phase)
        let stamp = SourceAge.preciseStamp(point.timestamp)
        let scoring = pregame ? nil : Self.play(point.scoringPlay)
        return Content(
            heading: title, stamp: stamp, home: home, away: away, score: score,
            badge: badge, stateAsOf: stateAsOf, play: scoring,
            spoken: spoken(heading: title, stamp: stamp, home: home, away: away, score: score,
                           badge: badge == point.phase?.word ? nil : badge,
                           stateAsOf: stateAsOf, play: scoring))
    }

    /// One VoiceOver sentence: the phase and its time, each named side's
    /// chance, the score with its own qualification, the game state, the play.
    /// A badge that only repeats the heading's phase is not said twice.
    private static func spoken(heading: String, stamp: String?, home: Side, away: Side,
                               score: Score, badge: String?, stateAsOf: String?,
                               play: Play?) -> String {
        var parts = ["\(heading), \(stamp ?? "time unknown")"]
        for side in [home, away] {
            parts.append(side.chance.map { "\(side.name) \($0)" } ?? "\(side.name) win chance unavailable")
        }
        switch score {
        case .hidden:
            break
        case .unavailable:
            parts.append(scoreUnavailable)
        case .pair(let note):
            if let h = home.score, let a = away.score {
                parts.append("Score: \(home.name) \(h), \(away.name) \(a)")
            }
            if let note { parts.append(note) }
        }
        let state = [badge, stateAsOf].compactMap { $0 }
        if !state.isEmpty { parts.append("Game state: " + state.joined(separator: ", ")) }
        if let play {
            parts.append("Play: " + [play.type, play.text].compactMap { $0 }.joined(separator: ", "))
        }
        return parts.joined(separator: ". ")
    }
}

/// The expanded, held reading of one chart moment. See
/// `ExpandedRecordedMatchMoment9483` for what it reads and where it may mount.
struct ExpandedRecordedMatchMomentView9483: View {
    let point: GamePlayPoint?
    let homeTeam: String
    let awayTeam: String
    var homeTeamColor: Color = .primary
    var awayTeamColor: Color = .primary
    var gameFinished = false

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var chanceSize: CGFloat = 28
    @ScaledMetric(relativeTo: .title2) private var scoreSize: CGFloat = 22

    private typealias Model = ExpandedRecordedMatchMoment9483

    var body: some View {
        if let content = Model.content(point: point, homeName: homeTeam, awayName: awayTeam,
                                       gameFinished: gameFinished) {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(content.heading).font(.headline)
                    Text(content.recordedLine)
                        .font(.subheadline)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
                .fixedSize(horizontal: false, vertical: true)
                competitors(content)
                scoreLine(content.score)
                state(content)
                if let play = content.play {
                    VStack(alignment: .leading, spacing: 2) {
                        if let type = play.type {
                            Text(type).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                        }
                        if let text = play.text {
                            Text(text).font(.subheadline)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(content.spoken)
        } else {
            Text(Model.unavailableTitle)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Side by side only when both blocks fit whole; otherwise they stack
    /// before a name or number squeezes, and accessibility sizes always stack.
    @ViewBuilder private func competitors(_ content: Model.Content) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 16) {
                side(content.home, homeTeamColor)
                side(content.away, awayTeamColor)
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 20) {
                    side(content.home, homeTeamColor).fixedSize()
                        .frame(maxWidth: .infinity, alignment: .leading)
                    side(content.away, awayTeamColor).fixedSize()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                VStack(alignment: .leading, spacing: 16) {
                    side(content.home, homeTeamColor)
                    side(content.away, awayTeamColor)
                }
            }
        }
    }

    private func side(_ side: Model.Side, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(side.name).font(.subheadline.weight(.semibold))
            VStack(alignment: .leading, spacing: 0) {
                Text(Model.chanceLabel).font(.caption).foregroundStyle(.secondary)
                if let chance = side.chance {
                    Text(chance)
                        .font(.system(size: chanceSize, weight: .bold).monospacedDigit())
                        .foregroundStyle(color)
                } else {
                    Text(Model.Side.unavailable).font(.body.weight(.semibold))
                }
            }
            if let score = side.score {
                VStack(alignment: .leading, spacing: 0) {
                    Text(Model.scoreLabel).font(.caption).foregroundStyle(.secondary)
                    Text(verbatim: "\(score)")
                        .font(.system(size: scoreSize, weight: .semibold).monospacedDigit())
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func scoreLine(_ score: Model.Score) -> some View {
        switch score {
        case .hidden:
            EmptyView()
        case .unavailable:
            Text(Model.scoreUnavailable)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
        case .pair(let note):
            if let note {
                Text(note)
                    .font(.footnote)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private func state(_ content: Model.Content) -> some View {
        if content.badge != nil || content.stateAsOf != nil {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) { stateParts(content) }
                VStack(alignment: .leading, spacing: 4) { stateParts(content) }
            }
        }
    }

    @ViewBuilder private func stateParts(_ content: Model.Content) -> some View {
        if let badge = content.badge {
            Text(badge)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(Color.gray.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
        if let asOf = content.stateAsOf {
            Text(asOf)
                .font(.subheadline)
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
