import SwiftUI

/// Live (red pulse with optional game clock), Scheduled countdown, Final (gray).
struct StatusBadge: View {
    let status: String?
    var commenceTime: String? = nil
    /// ESPN game clock, e.g., "5:42"
    var gameClock: String? = nil
    /// RAW ESPN period. The comment here used to claim `"Q3"` / `"3rd Period"`,
    /// and that is not what arrives: the real value is `"5:11 - 1st Quarter"`,
    /// with the clock on the FRONT (#3273). Both call sites pass
    /// `event.espn?.period` straight through.
    ///
    /// #9208 — the suspended arm reads it too, for the authority's stoppage
    /// word ("Postponed", "Canceled"). The team row has no `espn` block and
    /// passes the served `stoppage` here instead (``SearchEvent/authorityPeriod``).
    var period: String? = nil
    /// #6381 — the served `venue_settled`, and DEFAULTED FALSE on purpose.
    ///
    /// Only `/api/events/{id}` carries this key, so the event hero is the only
    /// call site that can pass a real value; the four card/row/schedule call
    /// sites have no way to know and keep the badge they have. Defaulting
    /// rather than requiring it is what keeps that true without four edits that
    /// would each have to invent a value.
    var venueSettled: Bool = false
    /// #8841 — the served `start_is_tbd`, defaulted false like `venueSettled`.
    /// True withholds the scheduled countdown: "In 3d 2h" is the placeholder
    /// clock restated as a duration, and the row's date line already carries
    /// the one true part ("Sep 29 · TBD"). See ``countdownText(commenceTime:startIsTbd:now:)``.
    var startIsTbd: Bool = false
    /// #5811 — the served `venue_closed_no_winner`, defaulted false like
    /// `venueSettled`. Unlike that key it rides every door (`/api/feed`,
    /// `/api/events/search` as well as `/api/events/{id}`), so the cards pass it
    /// too. A graded winner outranks it: see ``EventState/showsVenueClosedNoWinner(_:venueSettled:venueClosedNoWinner:commenceTime:now:)``.
    var venueClosedNoWinner: Bool = false
    /// #12616 / Ruling 182-A — on game cards (My Stuff, Sports, Discover), a
    /// capsule is ONLY for live status, and scheduled time is shown once as
    /// plain text (the date when days away, today/tomorrow clock when >= 1h, a
    /// countdown inside the last hour). Defaults false so non-card callers
    /// (`EventDetailView`, `SearchView`, `TeamDetailView`) keep their badge.
    var gameCardPlain182: Bool = false
    var gameCardLeadingDot: Bool = true

    /// #7019 — THE ONLY THING ON THIS VIEW THAT EVER CHANGES BY ITSELF.
    ///
    /// The scheduled arm's whole content is a clock, and every other input to it
    /// (`status`, `commenceTime`) is fixed for the life of the row. Reading the
    /// current instant implicitly inside `formatCountdown` therefore produced a
    /// string SwiftUI had no reason to redraw: a My Stuff row on a two-hour-old
    /// session read `In 1d 3h` beside its own `Tomorrow 1:10 PM`, and a cold
    /// relaunch of the same build read `In 1d 1h`. Observing the published
    /// instant is what re-evaluates `body`, and re-evaluating `body` — rather
    /// than just a timeline closure — is what lets the `if let` below collapse
    /// the chip to a true `EmptyView` once the kickoff passes. The reasoning for
    /// both halves is on `MinuteClock`.
    ///
    /// Not `private`: a `private` stored property makes Swift's memberwise
    /// initialiser `private` too, and all five call sites use it.
    @ObservedObject var clock = MinuteClock.shared

    /// Formatted live text: "Q1 5:11", "Bottom 7th", or "LIVE".
    ///
    /// #3273 — this read **"5:11 - 1st Quarter 5:11"** on the live Michigan game
    /// (photographed 2026-09-05), on the event hero AND on every sports feed
    /// card, because the raw period was joined to the clock it already contains.
    /// `PeriodLabel.liveBadgeLabel` shortens it while keeping baseball's
    /// half-inning, which is why "Bottom 7th" below is still whole.
    /// #4880 — the join, the meaningless-clock guard and the equality case all
    /// moved to `PeriodLabel.liveStatusText`, because five other surfaces print
    /// the same pair and only this one had any of the rules.
    private var liveText: String {
        PeriodLabel.liveStatusText(period: period, gameClock: gameClock) ?? "LIVE"
    }

    /// The arms are an if/else chain rather than a `switch` on purpose: the
    /// settled pair is `EventState.isFinished`, not two string literals this
    /// file gets to spell for itself. #4002 was one private copy of that
    /// vocabulary going stale; a badge is the last place a second copy belongs.
    @ViewBuilder
    var body: some View {
        if status == "live" {
            HStack(spacing: 4) {
                Circle()
                    .fill(.red)
                    .frame(width: 6, height: 6)
                    .modifier(PulseAnimation())
                Text(liveText)
                    .font(.caption2)
                    .fontWeight(.bold)
                    .foregroundStyle(.red)
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.red.opacity(0.1))
            .clipShape(Capsule())
        } else if EventState.isFinished(status) {
            if gameCardPlain182 {
                Text(gameCardLeadingDot ? "\u{00B7} Final" : "Final")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
            } else {
                Text("FINAL")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.cardBackgroundDark)
                    .clipShape(Capsule())
            }
        } else if EventState.showsVenueSettledVerdict(
            status, venueSettled: venueSettled, commenceTime: commenceTime?.asDate) {
            if gameCardPlain182 {
                Text(gameCardLeadingDot ? "\u{00B7} \(EventState.venueSettledLabel)" : EventState.venueSettledLabel)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
            } else {
                HStack(spacing: 3) {
                    Image(systemName: "checkmark.circle")
                        .font(.system(size: 8))
                    Text(EventState.venueSettledLabel)
                        .font(.caption2)
                        .fontWeight(.medium)
                }
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.cardBackgroundDark)
                .clipShape(Capsule())
            }
        } else if EventState.showsVenueClosedNoWinner(
            status, venueSettled: venueSettled, venueClosedNoWinner: venueClosedNoWinner,
            commenceTime: commenceTime?.asDate) {
            if gameCardPlain182 {
                Text(gameCardLeadingDot ? "\u{00B7} \(EventState.venueClosedNoWinnerLabel)" : EventState.venueClosedNoWinnerLabel)
                    .font(.caption)
                    .lineLimit(1)
                    .fixedSize()
                    .foregroundStyle(DS.textSecondaryReadable)
            } else {
                Text(EventState.venueClosedNoWinnerLabel)
                    .font(.caption2)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .fixedSize()
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.cardBackgroundDark)
                    .clipShape(Capsule())
            }
        } else if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime?.asDate) {
            if gameCardPlain182 {
                let word = EventState.suspendedLabel(authorityPeriod: period)
                Text(gameCardLeadingDot ? "\u{00B7} \(word)" : word)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
            } else {
                HStack(spacing: 3) {
                    Image(systemName: "exclamationmark.circle")
                        .font(.system(size: 8))
                    Text(EventState.suspendedLabel(authorityPeriod: period))
                        .font(.caption2)
                        .fontWeight(.medium)
                }
                .foregroundStyle(.orange)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(.orange.opacity(0.1))
                .clipShape(Capsule())
            }
        } else if status == "scheduled" {
            if gameCardPlain182 {
                if let when = StatusBadge.scheduledGameCardTimeText(
                    commenceTime: commenceTime, startIsTbd: startIsTbd, now: clock.now) {
                    Text(gameCardLeadingDot ? "\u{00B7} \(when)" : when)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                } else {
                    EmptyView()
                }
            } else {
                if let countdown = StatusBadge.countdownText(
                    commenceTime: commenceTime, startIsTbd: startIsTbd, now: clock.now) {
                    HStack(spacing: 3) {
                        Image(systemName: "clock")
                            .font(.system(size: 8))
                        Text("In \(countdown)")
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    // #12364 — the system blue on its own tint read about 2.9:1.
                    .foregroundStyle(DS.blueReadable)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(DS.blueReadable.opacity(0.1))
                    .clipShape(Capsule())
                } else {
                    EmptyView()
                }
            }
        } else {
            EmptyView()
        }
    }
}

extension StatusBadge {
    /// The scheduled arm's countdown ("2h 15m"), or nil for no chip.
    ///
    /// #8841 — lifted out of the `body` so the TBD withholding is a claim a test
    /// can make: a start the venue has not announced has no distance to count
    /// down to, so the chip is withheld rather than drawn off the placeholder.
    static func countdownText(
        commenceTime: String?, startIsTbd: Bool, now: Date
    ) -> String? {
        guard !startIsTbd, let date = commenceTime?.asDate else { return nil }
        return formatCountdown(from: date, now: now)
    }

    /// #12616 / Ruling 182-A — scheduled game-card time shown ONCE as plain text:
    /// - TBD start (#8841): `"Sep 29 · TBD"`
    /// - Inside the last hour (`0 < interval < 3600`): `"In 42m"` (countdown)
    /// - Today (`>= 1h` or at kickoff): `"Today 7:00 PM"`
    /// - Tomorrow (`>= 1h`): `"Tomorrow 3:30 PM"`
    /// - Days away (`2+` calendar days): the date (`"Sun, Nov 15"`, with year if
    ///   in another calendar year).
    static func scheduledGameCardTimeText(
        commenceTime: String?,
        startIsTbd: Bool,
        now: Date,
        calendar: Calendar = .current,
        timeZone: TimeZone = .current
    ) -> String? {
        if startIsTbd {
            return RelativeTimeText.tbdText(for: commenceTime)
        }
        guard let date = commenceTime?.asDate else { return nil }
        let interval = date.timeIntervalSince(now)
        if interval > 0 && interval < 3600 {
            guard let countdown = formatCountdown(from: date, now: now) else { return nil }
            return "In \(countdown)"
        }
        var cal = calendar
        cal.timeZone = timeZone
        let timeFormatter = DateFormatter()
        timeFormatter.calendar = cal
        timeFormatter.timeZone = timeZone
        timeFormatter.locale = Locale(identifier: "en_US_POSIX")
        timeFormatter.dateFormat = "h:mm a"

        if cal.isDate(date, inSameDayAs: now) {
            return "Today \(timeFormatter.string(from: date))"
        }
        if let tomorrow = cal.date(byAdding: .day, value: 1, to: now),
           cal.isDate(date, inSameDayAs: tomorrow) {
            return "Tomorrow \(timeFormatter.string(from: date))"
        }
        let dateFormatter = DateFormatter()
        dateFormatter.calendar = cal
        dateFormatter.timeZone = timeZone
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        let sameYear = cal.component(.year, from: date) == cal.component(.year, from: now)
        dateFormatter.dateFormat = sameYear ? "EEE, MMM d" : "EEE, MMM d, yyyy"
        return dateFormatter.string(from: date)
    }

    /// #12616 / Ruling 182-A — finished game-card status + date as plain text
    /// (`"Final · Nov 8"`, or `"Final"` when undated or future-dated).
    static func finishedGameCardTimeText(
        commenceTime: String?,
        now: Date,
        calendar: Calendar = .current,
        timeZone: TimeZone = .current
    ) -> String {
        guard let date = commenceTime?.asDate, date <= now else { return "Final" }
        var cal = calendar
        cal.timeZone = timeZone
        let formatter = DateFormatter()
        formatter.calendar = cal
        formatter.timeZone = timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let sameYear = cal.component(.year, from: date) == cal.component(.year, from: now)
        formatter.dateFormat = sameYear ? "MMM d" : "MMM d, yyyy"
        return "Final \u{00B7} \(formatter.string(from: date))"
    }
}

private struct PulseAnimation: ViewModifier {
    @State private var animating = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(animating ? 1.3 : 1.0)
            .opacity(animating ? 0.6 : 1.0)
            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: animating)
            .onAppear { animating = true }
    }
}
