import SwiftUI

/// #12307 / ruling 176-A — the clip's game page in its simple form: the app's
/// own event-page headline (Builder C's `EventSportHeadlineCard12472`, resolved
/// by `EventSportHeadlines12472` from the same `/api/events/{id}` the app reads),
/// then "Tell me how it ends" and "Get the app". The clip draws no headline of
/// its own: if the app's resolver has none for this game, neither does the clip.
@Observable
@MainActor
final class ClipGameModel12307 {
    let eventID: Int
    private(set) var event: EventDetail?
    /// The last read failed (an earlier event may still be on screen).
    private(set) var lastReadFailed = false

    init(eventID: Int) { self.eventID = eventID }

    /// The app's decoder settings (`APIClient`): snake case, nothing else.
    nonisolated static func decode(_ data: Data) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: data)
    }

    func refresh() async {
        guard let url = URL(string: "\(ClipInvocation12307.apiBase)/api/events/\(eventID)") else { return }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                lastReadFailed = true
                return
            }
            let next = try Self.decode(data)
            event = next
            lastReadFailed = false
        } catch {
            lastReadFailed = true
        }
    }
}

struct ClipGamePage12307: View {
    let event: EventDetail
    let now: Date
    let lastReadFailed: Bool
    let notify: ClipEndingAlert12307.State
    let tellMeHowItEnds: () -> Void
    let getApp: () -> Void

    @State private var showUpdateStream = false
    @State private var showProbabilityDetails = false

    /// The event page's own score rule (`EventDetailView.showsScore`).
    private var hasScore: Bool {
        guard event.awayScore != nil, event.homeScore != nil else { return false }
        return event.status == "live" || EventState.isFinished(event.status)
            || EventState.isSuspended(event.status)
    }

    /// The event page's own colours (`EventDetailView.teamColors`, rule 197).
    private var colors: (away: Color, home: Color) {
        TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor,
            awaySecondaryHex: event.awayTeamData?.secondaryColor,
            checkHueFamily: true)
    }

    private var headline: EventSportHeadlines12472.Model? {
        EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: PeriodLabel.liveStatusText(
                period: event.espn?.period, gameClock: event.espn?.gameClock),
            hasScore: hasScore,
            numberStreams: false,
            now: now)
    }

    private var isFinished: Bool { EventState.isFinished(event.status) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let headline {
                EventSportHeadlineCard12472(
                    model: headline,
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
                    revealForecast: nil)
                    .accessibilityIdentifier("clipHeadline")
            } else {
                // The app's page has no headline for this game yet; the clip
                // names the game and says so, in the page's words.
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(event.awayTeam) at \(event.homeTeam)")
                        .font(.title2.weight(.bold))
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    Text("No chance to show")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.secondary)
                }
                .accessibilityIdentifier("clipNoHeadline")
            }

            if lastReadFailed {
                Label("Not updated: Bain Luck couldn't be reached.", systemImage: "wifi.exclamationmark")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if !isFinished {
                ClipEndingAlertButton12307(state: notify, action: tellMeHowItEnds)
            }

            Button(action: getApp) {
                Text("Get the app")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .accessibilityIdentifier("clipGetApp")
        }
    }
}

/// "Tell me how it ends": one alert when this game finishes. An App Clip may
/// notify for 8 hours without asking, if the reader left that on in the clip's
/// card (`NSAppClipRequestEphemeralUserNotification`); the clip registers its
/// push token with the game as its only pin (177-A, `platform: appclip`).
enum ClipEndingAlert12307 {
    enum State: Equatable {
        case offered, working, set, unavailable
    }
}

struct ClipEndingAlertButton12307: View {
    let state: ClipEndingAlert12307.State
    let action: () -> Void

    var body: some View {
        switch state {
        case .offered, .working:
            Button(action: action) {
                Label("Tell me how it ends", systemImage: "bell")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .disabled(state == .working)
            .accessibilityIdentifier("clipTellMe")
        case .set:
            Label("We'll tell you how it ends", systemImage: "bell.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("clipTellMeSet")
        case .unavailable:
            Label("Alerts are off for Bain Luck", systemImage: "bell.slash")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("clipTellMeOff")
        }
    }
}
