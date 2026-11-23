import SwiftUI

// MARK: - Follow Button & Per-Team Game Card Follow Strip (Ruling 295: A · #11934)

/// One-tap Follow / Following button for ongoing subjects (team, league, and set pages).
/// No account required; after tapping Follow, reads "Following" and offers game alerts once on the page.
struct FollowButton295A: View {
    let subject: FollowedSubject295A
    var pageContextId: String? = nil
    var compact: Bool = false

    @Environment(\.followManager295A) private var followManager
    @Environment(\.gameAlertsPrompt295A) private var alertsPrompt

    var body: some View {
        FollowButtonBody295A(
            subject: subject,
            pageContextId: pageContextId,
            compact: compact,
            manager: followManager,
            alertsPrompt: alertsPrompt
        )
    }
}

private struct FollowButtonBody295A: View {
    let subject: FollowedSubject295A
    let pageContextId: String?
    let compact: Bool
    @ObservedObject var manager: FollowManager295A
    @ObservedObject var alertsPrompt: GameAlertsPromptController295A
    @Environment(\.colorScheme) private var colorScheme
    @ScaledMetric(relativeTo: .subheadline) private var labelFontSize: CGFloat = 14

    private var isFollowing: Bool {
        manager.isFollowing(subject)
    }

    private var effectiveFontSize: CGFloat {
        compact ? min(labelFontSize, 16) : min(labelFontSize, 18)
    }

    private var fillBackground: Color {
        if isFollowing {
            return colorScheme == .dark
                ? DS.emerald.opacity(0.18)
                : DS.emerald.opacity(0.12)
        }
        return colorScheme == .dark ? .white : DS.textPrimary
    }

    private var foregroundInk: Color {
        if isFollowing {
            return colorScheme == .dark ? DS.emerald : DS.greenReadable
        }
        return colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    private var borderStroke: Color {
        if isFollowing {
            return colorScheme == .dark ? DS.emerald.opacity(0.45) : DS.greenReadable.opacity(0.35)
        }
        return .clear
    }

    var body: some View {
        Button {
            let nowFollowing = manager.toggle(subject)
            if nowFollowing {
                let alertSubjectName = subject.kind == .team ? subject.name : ""
                if let pageContextId {
                    _ = alertsPrompt.offerInlineOnPage(contextId: pageContextId, subjectName: alertSubjectName)
                } else {
                    _ = alertsPrompt.offerSheet(subjectName: subject.kind == .team ? subject.name : nil)
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: isFollowing ? "checkmark" : "plus")
                    .font(.system(size: effectiveFontSize - 2, weight: .bold))
                Text(isFollowing ? "Following" : "Follow")
                    .font(.system(size: effectiveFontSize, weight: .semibold))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .foregroundStyle(foregroundInk)
            .padding(.horizontal, compact ? 11 : 14)
            .padding(.vertical, compact ? 6 : 8)
            .background(Capsule().fill(fillBackground))
            .overlay(Capsule().stroke(borderStroke, lineWidth: 1))
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(isFollowing ? "Following \(subject.name)" : "Follow \(subject.name)")
        .accessibilityIdentifier("followButton295A.\(subject.id)")
    }
}

/// One-tap Follow / Following buttons for each team on a game card (`EventCardView` & Discover game cards).
/// Withheld automatically on individual-sport events (tennis, golf, MMA, boxing).
struct GameCardTeamFollowBar295A: View {
    let event: FeedEventData

    @Environment(\.followManager295A) private var followManager
    @Environment(\.gameAlertsPrompt295A) private var alertsPrompt

    var body: some View {
        let pair = FollowedSubject295A.eventCardTeams(for: event)
        if pair.away != nil || pair.home != nil {
            GameCardTeamFollowBarBody295A(
                eventId: event.id,
                sportKey: event.sport,
                awayEntry: pair.away,
                homeEntry: pair.home,
                manager: followManager,
                alertsPrompt: alertsPrompt
            )
        }
    }
}

private struct GameCardTeamFollowBarBody295A: View {
    let eventId: Int
    let sportKey: String?
    let awayEntry: FollowedSubject295A.EventCardTeamEntry295A?
    let homeEntry: FollowedSubject295A.EventCardTeamEntry295A?
    @ObservedObject var manager: FollowManager295A
    @ObservedObject var alertsPrompt: GameAlertsPromptController295A
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Rectangle()
                .fill(Color.primary.opacity(colorScheme == .dark ? 0.08 : 0.06))
                .frame(height: 0.5)

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    if let awayEntry {
                        teamChip(entry: awayEntry, fullWidth: true)
                    }
                    if let homeEntry {
                        teamChip(entry: homeEntry, fullWidth: true)
                    }
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        if let awayEntry {
                            teamChip(entry: awayEntry, fullWidth: false)
                        }
                        if let homeEntry {
                            teamChip(entry: homeEntry, fullWidth: false)
                        }
                        Spacer(minLength: 0)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        if let awayEntry {
                            teamChip(entry: awayEntry, fullWidth: true)
                        }
                        if let homeEntry {
                            teamChip(entry: homeEntry, fullWidth: true)
                        }
                    }
                }
            }
        }
        .padding(.top, 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("gameCardTeamFollowBar295A.\(eventId)")
    }

    private func teamChip(entry: FollowedSubject295A.EventCardTeamEntry295A, fullWidth: Bool) -> some View {
        let subject = entry.subject
        let following = manager.isFollowing(subject)
        let nameInk: Color = colorScheme == .dark ? Color.white : DS.textPrimary
        let accentInk: Color = following
            ? (colorScheme == .dark ? DS.emerald : DS.greenReadable)
            : (colorScheme == .dark ? Color.white.opacity(0.75) : DS.textSecondaryReadable)
        let dotInk: Color = colorScheme == .dark ? Color.white.opacity(0.35) : DS.textMuted
        let bgFill: Color = following
            ? (colorScheme == .dark ? DS.emerald.opacity(0.16) : DS.emerald.opacity(0.10))
            : Color.primary.opacity(colorScheme == .dark ? 0.08 : 0.045)
        let strokeColor: Color = following
            ? (colorScheme == .dark ? DS.emerald.opacity(0.40) : DS.greenReadable.opacity(0.30))
            : Color.primary.opacity(colorScheme == .dark ? 0.12 : 0.08)

        return Button {
            let nowFollowing = manager.toggle(subject)
            if nowFollowing {
                _ = alertsPrompt.offerSheet(subjectName: subject.name)
            }
        } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .center, spacing: 6) {
                            TeamLogoView(
                                url: subject.logoUrl,
                                teamName: subject.name,
                                color: Color(hex: MyStuffTeamTextColour.logoTintHex(subject.primaryColor)),
                                size: 18,
                                sportKey: sportKey,
                                opponentName: entry.opponentName
                            )
                            Text(entry.shortName)
                                .font(.caption.weight(.medium))
                                .foregroundStyle(nameInk)
                                .lineLimit(nil)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        HStack(spacing: 4) {
                            Image(systemName: following ? "checkmark" : "plus")
                                .font(.caption2.weight(.bold))
                            Text(following ? "Following" : "Follow")
                                .font(.caption.weight(.semibold))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .foregroundStyle(accentInk)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 14).fill(bgFill))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(strokeColor, lineWidth: 1))
                } else {
                    HStack(spacing: 5) {
                        TeamLogoView(
                            url: subject.logoUrl,
                            teamName: subject.name,
                            color: Color(hex: MyStuffTeamTextColour.logoTintHex(subject.primaryColor)),
                            size: 15,
                            sportKey: sportKey,
                            opponentName: entry.opponentName
                        )

                        Text(entry.shortName)
                            .font(.caption.weight(.medium))
                            .foregroundStyle(nameInk)
                            .lineLimit(fullWidth ? 2 : 1)
                            .fixedSize(horizontal: !fullWidth, vertical: true)

                        if fullWidth {
                            Spacer(minLength: 6)
                        } else {
                            Text("·")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(dotInk)
                        }

                        HStack(spacing: 3) {
                            Image(systemName: following ? "checkmark" : "plus")
                                .font(.system(size: 9.5, weight: .bold))
                            Text(following ? "Following" : "Follow")
                                .font(.caption.weight(.semibold))
                                .lineLimit(1)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                        .foregroundStyle(accentInk)
                    }
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: 34, alignment: .leading)
                    .background(Capsule().fill(bgFill))
                    .overlay(Capsule().stroke(strokeColor, lineWidth: 1))
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(following ? "Following \(subject.name)" : "Follow \(subject.name)")
        .accessibilityIdentifier("gameCardFollow.\(eventId).\(subject.id)")
    }
}
