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
            Text("FINAL")
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.cardBackgroundDark)
                .clipShape(Capsule())
        } else if EventState.showsVenueSettledVerdict(
            status, venueSettled: venueSettled, commenceTime: commenceTime?.asDate) {
            // #6381 — ABOVE the suspended arm and below FINAL, and the order is
            // the whole point of putting it here rather than at the end of the
            // chain. 889 of the 1,471 rows the venue has graded are `suspended`,
            // so an arm placed after that one would never see them and the
            // bigger half of the class would keep printing "No result reported"
            // over a result we are holding. FINAL stays first because it says
            // this better: it has a score.
            //
            // Grey, not orange. The suspended badge is orange because it is
            // reporting an absence the reader may want to act on; this one
            // reports that the question is answered, which is the settled voice
            // FINAL already wears.
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
        } else if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime?.asDate) {
            // 🔴 #4021 — THE CLOCK IS PART OF THE TEST, and it has to be tested
            // HERE rather than left to callers. Three of this component's five
            // call sites (`SearchView` ×2, `TeamDetailView`) hand it a raw
            // `event.status`, so a suspended arm that trusted the status alone
            // would have put "No result reported" on a search row and a team
            // schedule row for event 416569 — Ohio State @ Texas, four days
            // BEFORE kick-off. Those callers now pass `commenceTime` too.
            //
            // A caller that passes none still gets the badge, matching
            // `EventState.hasStarted`'s documented default; a caller that passes
            // a FUTURE one falls through to `EmptyView`, which is exactly what
            // master did for it, so no surface loses a badge it had.
            //
            // #4002 — the state that had no badge at all. It cannot borrow
            // FINAL's grey silence: FINAL is read against a score, and this one
            // is read against a hero that may have nothing else on it. The
            // wording is `EventState.suspendedLabel` and NOT the bare word
            // "Suspended" for the reason stated where it is defined — the same
            // status covers a rain delay and a source going dark, and only one
            // of those is a stoppage anybody reported.
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.circle")
                    .font(.system(size: 8))
                Text(EventState.suspendedLabel)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.orange)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.orange.opacity(0.1))
            .clipShape(Capsule())
        } else if status == "scheduled" {
            // #7019 — `clock.now` and not an implicit `Date()`. Passing it is
            // what makes this arm a reader of something that changes; drop the
            // argument and the chip compiles, draws correctly once, and then
            // silently stops ageing on every surface at once.
            if let countdown = StatusBadge.countdownText(
                commenceTime: commenceTime, startIsTbd: startIsTbd, now: clock.now) {
                HStack(spacing: 3) {
                    Image(systemName: "clock")
                        .font(.system(size: 8))
                    Text("In \(countdown)")
                        .font(.caption2)
                        .fontWeight(.medium)
                }
                .foregroundStyle(.blue)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(.blue.opacity(0.1))
                .clipShape(Capsule())
            } else {
                EmptyView()
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
