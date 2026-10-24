import SwiftUI

/// #2920 / #9483 — THE LIVE PROJECTED FINAL, READ FROM THE ROW EACH SURFACE HOLDS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: a live card and the event page it opens
/// show the same supported projected final, beside the actual score and never
/// instead of it.
///
/// `LiveProjectedFinalAdmission2920` decides; this file only hands it the row:
/// `currentOdds.liveProjection` and nothing else, the row's own start, the
/// score the surface PRINTS, and soccer's phase from the served period (`espn.period`, the field the producer's own
/// regulation test reads). No clock of its own beyond the caller's `now`, no
/// fetch, no state: a pushed score or period re-renders the surface and this
/// answers again; a pushed probability leaves the object as it was.
///
/// Web's halves, ported: the cards are `liveCardProjectedFinal` (FeedCard,
/// EventCard), the page is `eventPageProjectedPair` (`projectedFinalPair.ts`).
enum LiveProjectedFinal2920 {

    /// The one call both surfaces make.
    static func resolve(
        odds: CurrentOdds?, sport: String?, status: String?,
        commenceTime: String?,
        homeScore: Int?, awayScore: Int?, servedPeriod: String?,
        now: Date
    ) -> LiveProjectedFinalAdmission2920.Outcome {
        LiveProjectedFinalAdmission2920.resolve(
            projection: odds?.liveProjection,
            sport: sport, status: status,
            rowStart: .init(commenceTime: commenceTime),
            homeScore: homeScore, awayScore: awayScore,
            phase: LiveProjectedFinalAdmission2920.soccerPhase(servedPeriod: servedPeriod),
            now: now)
    }

    /// A live card's line, or nil. Both native cards print the row's score
    /// while it is live, so the score handed in is the one on the card.
    static func card(_ event: FeedEventData, now: Date = Date()) -> LiveProjectedFinalAdmission2920.Printed? {
        resolve(odds: event.currentOdds, sport: event.sport, status: event.status,
                commenceTime: event.commenceTime,
                homeScore: event.homeScore, awayScore: event.awayScore,
                servedPeriod: event.espn?.period, now: now).printed
    }

    /// What the event page's projected-final slot reads for this row.
    enum PagePair: Equatable {
        /// Not a live game that has started: the page's pre-game rule stands.
        case notLive
        /// The producer's in-play pair, admitted for this row and its score.
        case admitted(LiveProjectedFinalAdmission2920.Printed)
        /// An in-play object was served and refused: the slot prints nothing,
        /// never the bare `projected_*` pair or the ladders — the card one tap
        /// back reads the same object and prints nothing too.
        case withheld
        /// No in-play object served. Compatibility only, and web's rule: the
        /// ladders' in-game pair (`pm_spread_data.projected_final`) under the
        /// page's own gates. Never the bare pair, which can be pregame.
        case absent
    }

    /// Web's `eventPageProjectedPair` live arm. "Live" is the card's own test —
    /// served `live` and the start not still ahead — so the page and the card
    /// one tap back switch together.
    static func page(_ event: EventDetail, now: Date = Date()) -> PagePair {
        guard event.status == "live" else { return .notLive }
        if let start = event.commenceTime?.asDate, start > now { return .notLive }
        // Absent is the object's absence, as web tests `live_projection` for
        // null; anything served goes through the helper.
        guard event.currentOdds?.liveProjection != nil else { return .absent }
        let outcome = resolve(
            odds: event.currentOdds, sport: event.sport, status: event.status,
            commenceTime: event.commenceTime,
            homeScore: event.homeScore, awayScore: event.awayScore,
            servedPeriod: event.espn?.period, now: now)
        switch outcome {
        case .printed(let printed): return .admitted(printed)
        case .withheld: return .withheld
        }
    }

    /// The visible pair in the card's own order — both native cards stack away
    /// over home — each score glued to its team by a no-break space, as the
    /// finished-card line does (`FinalForecastComparison11296.pairText`).
    nonisolated static func pairText(_ p: LiveProjectedFinalAdmission2920.Printed,
                                     awayName: String, homeName: String) -> String {
        "\(awayName)\u{00A0}\(p.away) · \(homeName)\u{00A0}\(p.home)"
    }

    /// One sentence for assistive tech that names both teams.
    nonisolated static func spokenText(_ p: LiveProjectedFinalAdmission2920.Printed,
                                       awayName: String, homeName: String) -> String {
        "\(p.label): \(awayName) \(p.away), \(homeName) \(p.home)"
    }
}

/// The line both live cards draw under the actual score: the label, then both
/// named teams' projected points. Caption size and secondary colour, so the
/// live score above stays the primary number. One view so the two cards cannot
/// drift — the finished cards' `FinalForecastLine11296` anatomy, holding a
/// different quantity.
///
/// #11422 — ONE LINE AT NORMAL TEXT SIZE. The full names ("Indiana Pacers 117 ·
/// New Orleans Pelicans 121") under a stacked label drew three lines on an
/// iPhone, a paragraph under a card whose rows already name both teams. The
/// visible pair uses the card's short names (`TeamShortName.shortPair`, which
/// grows a pair that would collide) beside the label on one line; when even
/// that does not fit — the larger text sizes — the label stacks over the pair
/// and both wrap. VoiceOver keeps the full names.
struct LiveProjectedFinalLine2920: View {
    let printed: LiveProjectedFinalAdmission2920.Printed
    let awayName: String
    let homeName: String
    let sportKey: String?

    static let accessibilityIdentifier = "live-projected-final-2920"

    /// What the reader sees after the label: the pair in short names.
    nonisolated static func visiblePair(_ printed: LiveProjectedFinalAdmission2920.Printed,
                                        awayName: String, homeName: String,
                                        sportKey: String?) -> String {
        let short = TeamShortName.shortPair(away: awayName, home: homeName, sportKey: sportKey)
        return LiveProjectedFinal2920.pairText(printed, awayName: short.away, homeName: short.home)
    }

    var body: some View {
        let pair = Self.visiblePair(printed, awayName: awayName, homeName: homeName, sportKey: sportKey)
        ViewThatFits(in: .horizontal) {
            Text("\(printed.label): \(pair)")
                .lineLimit(1)
            VStack(alignment: .leading, spacing: 2) {
                Text(printed.label)
                Text(pair)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            LiveProjectedFinal2920.spokenText(printed, awayName: awayName, homeName: homeName))
        .accessibilityIdentifier(Self.accessibilityIdentifier)
    }
}
