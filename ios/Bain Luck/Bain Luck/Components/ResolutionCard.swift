import SwiftUI

/// Collapses N resolution notes into a single digest card (#902 item 8) so the
/// feed top isn't a stack of "RESOLVED" cards. Taps through to prediction stats.
struct NativeResolutionDigestCard: View {
    let total: Int
    let correct: Int

    private var headline: String {
        let noun = total == 1 ? "prediction" : "predictions"
        return "\(total) \(noun) resolved"
    }

    private var subline: String {
        "\(correct) right"
    }

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color.purple.opacity(0.12))
                    .frame(width: 44, height: 44)
                Image(systemName: "checklist")
                    .font(.body.weight(.bold))
                    .foregroundStyle(.purple)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text("RESOLVED")
                    .font(.caption2.weight(.heavy))
                    .tracking(0.8)
                    .foregroundStyle(.purple)

                Text(headline)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)

                Text(subline)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.barTrack.opacity(0.55), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2)
    }
}

/// What a refresh started from the BOTTOM of the feed is doing — which, until
/// #1472, the reader had no way at all to know.
///
/// #1773 gave `NativeFeedEndCard` its own Refresh button because the gesture the
/// card named was unreachable where the card is. The button works: it runs
/// `DiscoverView.refreshFeed()`. What it does not do is say so, and every signal
/// that would have said so for it is absent at this end of the page:
///
///   • **No spinner.** `DiscoverViewModel.load()` raises its blocking `loading`
///     flag only `if items.isEmpty` — by design, so a revalidation happens
///     silently behind last-good content instead of blanking it (#1465). At the
///     bottom of a populated feed `items` is never empty, so nothing spins.
///   • **No error.** A failed refresh sets `refreshFailedShowingCache`, and the
///     banner that reads it is drawn at the TOP of the scroll view. This card is
///     the bottom of the same scroll view, so the reader who pressed the button
///     is the one reader who cannot see the answer.
///   • **No change in the cards.** A refresh that returns the same markets is a
///     correct refresh, and the common case.
///
/// So all three outcomes — in flight, done, failed — render byte-identically to
/// not having pressed it. Alex's September 16 physical-phone test: "Bottom
/// Refresh produces no visible response or loading feedback."
enum NativeFeedRefreshPhase: Equatable {
    /// Nothing has been asked for, or the confirmation for the last refresh has
    /// expired. "Checked just now" must not still be on screen ten minutes later.
    case idle
    /// A refresh is in flight. The control is not tappable in this phase — a
    /// second tap would bump `visibleCount` and the dismiss store again for a
    /// request already on the wire.
    case refreshing
    /// The last refresh completed and the feed is current. Decays back to `idle`.
    case refreshed
    /// The last refresh failed. Does NOT decay: it is the reader's only notice,
    /// and it carries the retry.
    case failed
}

/// The whole of what the reader can see about a refresh they started here.
///
/// One value rather than four scattered reads, because the property #1472 is
/// about is a property of the SET: before this, all four phases produced the
/// same pixels. `testEveryPhaseLooksDifferentFromEveryOther` is the test that
/// states it.
struct NativeFeedRefreshPresentation: Equatable {
    /// The control's label.
    let title: String
    /// The control's leading glyph, or `nil` to draw a progress spinner there.
    let systemImage: String?
    /// Whether the control accepts a tap.
    let isEnabled: Bool
    /// One short line under the control, or `nil` for none.
    let status: String?
    /// What the control is called to a reader who cannot see it.
    ///
    /// Carried in the rule rather than composed at the view, because a `Button`
    /// with an explicit `.accessibilityLabel` **replaces** its children in the
    /// accessibility tree: the `Text(title)` inside it stops being an element of
    /// its own. A single fixed label therefore reproduces #1472 exactly, one
    /// reader over — every phase announcing "Refresh feed" is the audible
    /// equivalent of every phase drawing the same pixels. Measured: the journey
    /// test could not find "Refreshing…" anywhere in the tree after a real tap
    /// on a real build, because of this.
    let accessibilityLabel: String
}

/// Honest end-of-feed card (#902 item 9) shown once pagination is exhausted.
/// Cadence ("every couple of hours") is derived from the documented ingestion
/// poll cadences (Polymarket every 1h, Kalshi every 2h) — see CLAUDE.md.
struct NativeFeedEndCard: View {
    /// #1773: when present, the card carries its own Refresh control instead of
    /// naming a gesture the reader cannot perform where the card is.
    var onRefresh: (() -> Void)? = nil

    /// #1472. **Deliberately has no default.** A phase that defaulted to `.idle`
    /// would let a call site that never wires the state compile clean and ship
    /// this whole fix disarmed, with every unit test still green — each test
    /// builds its own card and none of them can see the real page. Making the
    /// compiler ask each call site is the cheapest guard against that, and
    /// `testBothEndCardCallSitesPassTheLiveRefreshPhase` reads the two of them as
    /// text in case someone answers the compiler with a literal.
    let phase: NativeFeedRefreshPhase

    /// Pure copy rule, unit-tested (#1773).
    ///
    /// This card renders at the BOTTOM of the Discover feed, where
    /// `.refreshable`'s pull-down is unreachable — the reader would have to
    /// scroll all the way back to the top to perform the gesture the card just
    /// asked for. Alex's report names exactly that: "when I get to the bottom,
    /// it invites me to pull to refresh, but I can't pull up, and scrolling back
    /// to the top just to pull down feels counterintuitive."
    ///
    /// So: only name the gesture when there is no button to press instead.
    static func bodyCopy(hasRefreshAction: Bool) -> String {
        hasRefreshAction
            ? "New markets surface roughly every couple of hours."
            : "New markets surface roughly every couple of hours — pull to refresh."
    }

    /// Pure presentation rule, unit-tested (#1472).
    ///
    /// The four phases have to be distinguishable from each other on sight AND
    /// by ear — that is the entire defect, and it has two readers. Each phase
    /// changes the title, the glyph, or the status line; each also changes the
    /// accessibility label, because the button's label replaces its children.
    /// `.refreshing` is the only phase that refuses a tap.
    static func refreshPresentation(_ phase: NativeFeedRefreshPhase) -> NativeFeedRefreshPresentation {
        switch phase {
        case .idle:
            return NativeFeedRefreshPresentation(
                title: "Refresh", systemImage: "arrow.clockwise", isEnabled: true, status: nil,
                accessibilityLabel: "Refresh feed")
        case .refreshing:
            // `systemImage: nil` is the spinner's seat. The reader must see the
            // press land in the same frame as the press.
            return NativeFeedRefreshPresentation(
                title: "Refreshing…", systemImage: nil, isEnabled: false, status: nil,
                accessibilityLabel: "Refreshing the feed")
        case .refreshed:
            // Says what was checked, never what was found: a refresh that returns
            // the same markets is a correct refresh, and "new markets" would be a
            // claim this card cannot make.
            return NativeFeedRefreshPresentation(
                title: "Refresh", systemImage: "arrow.clockwise", isEnabled: true,
                status: "Checked just now",
                accessibilityLabel: "Refresh feed. Checked just now.")
        case .failed:
            return NativeFeedRefreshPresentation(
                title: "Try again", systemImage: "arrow.clockwise", isEnabled: true,
                status: "Couldn't refresh",
                accessibilityLabel: "Couldn't refresh. Try again.")
        }
    }

    var body: some View {
        let control = Self.refreshPresentation(phase)
        return VStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .font(.title)
                .foregroundStyle(.green)
            Text("You're all caught up")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.primary)
            Text(Self.bodyCopy(hasRefreshAction: onRefresh != nil))
                .font(.caption)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            if let onRefresh {
                Button(action: onRefresh) {
                    HStack(spacing: 6) {
                        if let systemImage = control.systemImage {
                            Image(systemName: systemImage)
                        } else {
                            ProgressView()
                                .controlSize(.small)
                        }
                        Text(control.title)
                    }
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(control.isEnabled ? Color.blue : Color.secondary)
                    .frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .disabled(!control.isEnabled)
                .accessibilityLabel(control.accessibilityLabel)
                .accessibilityHint("Checks for newly surfaced markets")

                if let status = control.status {
                    // The sighted reader's copy of what the label above already
                    // says. Hidden from the accessibility tree rather than
                    // labelled, so VoiceOver does not read the outcome twice.
                    Text(status)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28)
        .padding(.horizontal, 16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.barTrack.opacity(0.45), lineWidth: 1)
        )
    }
}
