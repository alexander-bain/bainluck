import SwiftUI

/// Step 1 (`1A` / `1B` of 212-A, #11934): native shared-game arrival view with zero sign-in wall.
///
/// Honors all four of Fable's Nov 16 adjustments:
/// 1. Uses the shipped `EventSportHeadlineCard12472` (`Proj. · Chance` before game,
///    `Score · Proj. · Now` with grey pregame line during play — never a custom hero).
/// 2. Fitted win-chance chart (`OddsChartView` without forced `0–100` domain per ruling `201`).
/// 3. Zero redundant `"Pregame (61%) Projected: ..."` clutter strip under the chart.
/// 4. Wording strictly in `"points"` (never `"pts"`).
///
/// Underneath, `"More of what the world thinks now"` peeks live non-sports & sports cards while
/// the fixed bottom `"Want start & swing updates?"` bookmark bar lets the reader pin without
/// an account (`Step 3`) and triggers `#13084`'s contextual alert prompt (`Step 4A`).
struct SharedLinkArrivalView212A: View {
    let event: EventDetail
    var preloadedHistory: EventHistoryResponse? = nil
    var arrivedHeadline: String? = nil
    let moreCards: [FirstRunCard212A]
    let onOpenFullGame: () -> Void
    let onOpenDiscover: () -> Void
    var onSelectMoreCard: ((FirstRunCard212A) -> Void)? = nil

    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.colorScheme) private var colorScheme
    @State private var chartRange: OddsTimeRange = .sinceStart
    @State private var showUpdateStream = false
    @State private var showProbabilityDetails = false

    private var resolvedArrivalHeadline: String? {
        FirstRunLinkHandoffBridge212A.resolvedHeadline(explicit: arrivedHeadline)
    }

    private var colors: (away: Color, home: Color) {
        TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor,
            awaySecondaryHex: event.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )
    }

    private var headlineModel: EventSportHeadlines12472.Model {
        EventDetailView.resolvedHeadlineModel(for: event)
    }

    private var isPinned: Bool {
        pinManager.isPinned(type: "event", id: event.id)
    }

    var body: some View {
        VStack(spacing: 0) {
            topStrip
                .padding(.horizontal, 16)
                .padding(.vertical, 10)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let headline = resolvedArrivalHeadline {
                        HStack(spacing: 8) {
                            Image(systemName: "link.circle.fill")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.blueReadable)
                                .accessibilityHidden(true)
                            Text(FirstRunLinkHandoffBridge212A.bannerText(headline: headline))
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 4)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 9)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(DS.blueReadable.opacity(0.4), lineWidth: 1)
                        )
                        .accessibilityIdentifier("sharedArrival212A.handoffBanner")
                    }

                    VStack(spacing: 0) {
                        EventSportHeadlineCard12472(
                            model: headlineModel,
                            colors: colors,
                            ekgTracker: .empty,
                            liveUpdateStatus: .hidden,
                            displayAsOf: nil,
                            updateStream: LiveUpdateStream(),
                            showUpdateStream: $showUpdateStream,
                            showProbabilityDetails: $showProbabilityDetails,
                            priceStreamingEligible: false,
                            lastReceivedAt: nil,
                            confirmedAt: nil,
                            revealForecast: nil
                        )

                        OddsChartView(
                            eventId: event.id,
                            teamColors: colors,
                            commenceTime: event.commenceTime,
                            status: event.status,
                            venueSettled: event.venueSettled == true,
                            homeTeamName: event.homeTeam,
                            awayTeamName: event.awayTeam,
                            homeTeamLogo: event.homeTeamData?.logoSmall,
                            awayTeamLogo: event.awayTeamData?.logoSmall,
                            homeTeamAbbrev: event.homeTeamData?.abbreviation,
                            awayTeamAbbrev: event.awayTeamData?.abbreviation,
                            sportKey: event.sport,
                            homeScore: event.homeScore,
                            awayScore: event.awayScore,
                            servedSettledResult: event.heroSettledResult,
                            refreshStreaming: false,
                            liveUpdateStatus: .hidden,
                            priceActivity: nil,
                            liveEdgeShowsPreview: false,
                            liveEdge: nil,
                            quoteIsCurrent: true,
                            pairedAwayLabel9483: nil,
                            servedHomeProbability: event.currentOdds?.homeProbability,
                            servedAwayProbability: event.currentOdds?.awayProbability,
                            forcedDomain: nil,
                            legacyDataDomain: nil,
                            selectedRange: $chartRange,
                            preloadedHistory: preloadedHistory
                        )
                    }
                    .background(EventDetailView.heroBackdrop(colors))
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(DS.border, lineWidth: 1)
                    )

                    moreSection
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 20)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }

            fixedPinBar
        }
        .background(DS.surface)
    }

    private var topStrip: some View {
        HStack(spacing: 8) {
            Text("\u{1F340}")
                .font(.headline)
            Text("Bain Luck")
                .font(.headline.weight(.bold))
                .foregroundStyle(DS.textPrimary)
            Spacer()
            Button(action: onOpenFullGame) {
                HStack(spacing: 3) {
                    Text("Full game")
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.blueReadable)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("sharedArrival212A.fullGame")
        }
    }

    private var moreSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("More of what the world thinks now")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Button("Discover \u{2192}", action: onOpenDiscover)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
            }

            ForEach(moreCards) { card in
                Button {
                    onSelectMoreCard?(card)
                } label: {
                    moreCardRow(card)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func moreCardRow(_ card: FirstRunCard212A) -> some View {
        let tint = Color(hex: MyStuffTeamTextColour.probabilityHex(card.accentHex, colorScheme: colorScheme))
        return HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    if let kicker = card.kicker, !kicker.isEmpty {
                        Text(kicker)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(tint)
                    }
                    if let shift = FirstRunCard212A.shiftText(points: card.deltaPoints) {
                        Text(shift)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle((card.deltaPoints ?? 0) >= 0 ? DS.greenReadable : DS.danger)
                    }
                }
                Text(card.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                if let detail = card.detailLine, !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 1) {
                Text("\(card.percent)%")
                    .font(.headline.weight(.heavy).monospacedDigit())
                    .foregroundStyle(tint)
                Text(card.percentLabel)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondaryReadable)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    private var fixedPinBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Want start & swing updates?")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Pin to this iPhone \u{00B7} No account needed")
                    .font(.caption2)
                    .foregroundStyle(Color.white.opacity(0.75))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Button {
                let wasPinned = isPinned
                pinManager.togglePin(type: "event", id: event.id)
                if !wasPinned, pinManager.isPinned(type: "event", id: event.id) {
                    _ = GameAlertsPromptController295A.shared.offerSheet(subjectName: nil)
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: isPinned ? "bookmark.fill" : "bookmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(isPinned ? .orange : Color(hex: "#0F172A"))
                    Text(isPinned ? "Pinned" : "Pin Game")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(Color(hex: "#0F172A"))
                }
                .padding(.horizontal, 14)
                .frame(minHeight: 38)
                .background(.white, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("sharedArrival212A.pinButton")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color(hex: "#111827"))
    }
}
