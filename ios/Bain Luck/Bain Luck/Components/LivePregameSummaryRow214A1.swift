import Foundation
import SwiftUI

/// Rulings 213-A + 214-A1 — shared live pregame summary resolver for phone cards
/// (`FeedEventData` on Discover, feed, and search) and shared single-line
/// team-coloured view mounted on both the phone game page and the phone cards.
enum LivePregameCardSummary213A {

    /// Builds the page's exact live pregame summary (`"Pregame  Lions 58% · projected 27–24"`)
    /// for Discover, feed, and search cards, using served `prematch_odds` (never
    /// `opening_odds`) and qualified pregame sportsbook projections.
    nonisolated static func resolve(
        event: FeedEventData
    ) -> EventSportHeadlines12472.LivePregameSummary? {
        let isSuspended = EventState.isSuspendedAndStarted(
            event.status,
            commenceTime: event.commenceTime?.asDate
        )
        guard event.status == "live", !isSuspended else { return nil }

        let shortNames = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )
        let projPair = EventSportHeadlines12472.qualifiedPregameProjectionPair(
            projection: event.pregameProjection,
            sport: event.sport,
            status: event.status,
            commenceTime: event.commenceTime
        )

        if CompactGameCard12616.hasExplicitThreeWayPrematch(event),
           let pre = event.prematchOdds,
           let home = CompactGameCard12616.usableProbability(pre.homeProbability),
           let draw = CompactGameCard12616.usableProbability(pre.drawProbability),
           let away = CompactGameCard12616.usableProbability(pre.awayProbability) {
            let texts = EventSportHeadlines12472.soccerThreeWayChanceTexts(
                home: home,
                draw: draw,
                away: away,
                numberStreams: false
            )
            let chanceInfo: (
                namedInk: EventSportHeadlines12472.LivePregameSummary.SegmentInk,
                homeIsFav: Bool,
                favName: String,
                favChanceText: String
            )
            if home >= away && home >= draw {
                chanceInfo = (.homeTeam, true, shortNames.home, texts.home)
            } else if away >= home && away >= draw {
                chanceInfo = (.awayTeam, false, shortNames.away, texts.away)
            } else {
                chanceInfo = (.drawOutcome, projPair.map { $0.home >= $0.away } ?? true, "Draw", texts.draw)
            }
            return EventSportHeadlines12472.formatLivePregameSummary(
                chanceInfo: chanceInfo,
                projPair: projPair,
                shortNames: shortNames
            )
        }

        let strictPregame = PrematchReading.resolve(
            prematch: event.prematchOdds,
            opening: nil
        )
        var chanceInfo: (
            namedInk: EventSportHeadlines12472.LivePregameSummary.SegmentInk,
            homeIsFav: Bool,
            favName: String,
            favChanceText: String
        )?

        if let strictPregame,
           let pair = DrawPricedWinner.printablePair(
               away: strictPregame.awayProbability,
               home: strictPregame.homeProbability,
               sport: event.sport
           ),
           let awayP = pair.away {
            let homeP = pair.home
            let homeIsFav: Bool
            if homeP > awayP {
                homeIsFav = true
            } else if awayP > homeP {
                homeIsFav = false
            } else if let projPair, projPair.home != projPair.away {
                homeIsFav = projPair.home > projPair.away
            } else {
                homeIsFav = true
            }
            let favName = homeIsFav ? shortNames.home : shortNames.away
            let favProb = homeIsFav ? homeP : awayP
            let favRendered = homeIsFav
                ? (strictPregame.percents.count > 1 ? strictPregame.percents[1] : nil)
                : (strictPregame.percents.count > 0 ? strictPregame.percents[0] : nil)
            let favChanceText = formatProbability(favProb, renderedPercent: favRendered)
            chanceInfo = (
                namedInk: homeIsFav ? .homeTeam : .awayTeam,
                homeIsFav: homeIsFav,
                favName: favName,
                favChanceText: favChanceText
            )
        } else if let strictPregame,
                  let pair = DrawPricedWinner.printablePair(
                      away: strictPregame.awayProbability,
                      home: strictPregame.homeProbability,
                      sport: event.sport
                  ) {
            let homePct = strictPregame.percents.count > 1 ? strictPregame.percents[1] : nil
            chanceInfo = (
                namedInk: .homeTeam,
                homeIsFav: true,
                favName: shortNames.home,
                favChanceText: formatProbability(pair.home, renderedPercent: homePct)
            )
        }

        return EventSportHeadlines12472.formatLivePregameSummary(
            chanceInfo: chanceInfo,
            projPair: projPair,
            shortNames: shortNames
        )
    }
}

/// Rulings 213-A + 214-A1 — shared single-line live pregame summary view mounted
/// on the phone game page (`EventSportHeadlineCard12472`) and on Discover, feed,
/// and search cards (`DiscoverCompactSingleGameCard190CView`, `EventCardView`).
///
/// Prints `"Pregame  Lions 58% · projected 27–24"` on one line that never wraps,
/// with `"Lions 58%"` and `27` in the Lions' colour (named team first) and `24`
/// in the other team's colour, following Ruling 197 for same-family and
/// slate-fallback pairs.
struct LivePregameSummaryRow214A1: View {
    let summary: EventSportHeadlines12472.LivePregameSummary
    let surface: HeadlineStyleTable199.Surface
    let colors: (away: Color, home: Color)
    var scaledSize: CGFloat? = nil
    var minScale: CGFloat = 0.78
    var accessibilityIdentifier: String = "live-pregame-summary-214a1"

    /// Neutral quiet connector grey (`#767C85`, regular weight) so connecting prose
    /// (`" · projected "`, `"–"`) stays visually lighter and neutral beside a team on
    /// Ruling 197's `#64748B` cool slate fallback.
    private static let connectorInk = Color(red: 118.0 / 255.0, green: 124.0 / 255.0, blue: 133.0 / 255.0)

    var body: some View {
        composedText
            .font(HeadlineStyleTable199.quietText(surface, monospacedDigits: true, scaledSize: scaledSize))
            .lineLimit(1)
            .minimumScaleFactor(minScale)
            .allowsTightening(true)
            .truncationMode(.tail)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel("\(summary.leadWord), \(summary.bodyText)")
            .accessibilityIdentifier(accessibilityIdentifier)
    }

    private var composedText: Text {
        summary.segments.reduce(Text("")) { partial, seg in
            switch seg.ink {
            case .quietLead:
                return partial + Text(seg.text)
                    .fontWeight(.semibold)
                    .foregroundColor(HeadlineStyleTable199.quietInk)
            case .quiet:
                return partial + Text(seg.text)
                    .fontWeight(.regular)
                    .foregroundColor(Self.connectorInk)
            case .awayTeam:
                return partial + Text(seg.text)
                    .fontWeight(.bold)
                    .foregroundColor(colors.away)
            case .homeTeam:
                return partial + Text(seg.text)
                    .fontWeight(.bold)
                    .foregroundColor(colors.home)
            case .drawOutcome:
                return partial + Text(seg.text)
                    .fontWeight(.bold)
                    .foregroundColor(HeadlineStyleTable199.drawInk)
            }
        }
    }
}
