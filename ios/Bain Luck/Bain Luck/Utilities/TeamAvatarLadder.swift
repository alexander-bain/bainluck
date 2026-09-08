import Foundation

// MARK: - Team Avatar Ladder (#2977)

/// The ONE ladder that decides which picture a team gets.
///
/// `TeamLogoView` — the Sports row — already had it: served url → client-derived
/// flag → ESPN-by-name → a coloured fallback. `DiscoverEventCard.heroTeam` and
/// `DiscoverView.teamBadge` each had a private, shorter one: served url, else a
/// letter tile. So one launch drew the Dodgers crest on the Sports tab and a flat
/// blue "DOD" square on Discover, for the same game (#2977).
///
/// **Measured before building, on the production page of 2026-09-08**
/// (`/api/feed?limit=200&event_pct=0.6` — 59 event cards, 118 sides):
///
/// - 95 of 118 sides arrive with **no avatar url of any kind**;
/// - 51 of those 95 are teams `espnTeamLogoURL(for:)` names — every MLB team on
///   the page, the Cardinals included;
/// - only 8 of the 59 cards carried a `*_team_data` block at all.
///
/// That last number is why this is a ladder problem and not an image-coverage
/// problem: the crest the two Discover surfaces were waiting for mostly never
/// comes, and the rung that would have found it anyway lived inside a view they
/// do not use. The issue's own framing — one bad team, the Cardinals fine — is
/// falsified by the page above, where both sides of most MLB cards are bare.
///
/// `ParticipantAvatar`'s doc comment already promised this: a nil url "hands the
/// decision back to the view's own ladder". These two views had no ladder to hand
/// it back to. Lifting the rungs out of `TeamLogoView` is the point — a ladder
/// that lives inside one view is a ladder the next surface re-invents shorter.

/// Which url a team avatar should try, in the Sports row's order.
///
/// Returns nil only when no rung produced one; the caller then draws its own
/// fallback, which is deliberately not shared — the Discover hero's coloured tile
/// carries a three-letter abbreviation and `TeamLogoView`'s carries one initial,
/// and each is right for the size it is drawn at. What must be shared is the
/// *decision*, not the consolation prize.
func teamAvatarURL(servedURL: String?, teamName: String, sportKey: String? = nil) -> String? {
    // An empty string is not a url. It arrives from a payload that has the key
    // but nothing behind it, and treating it as one blanks the slot.
    if let servedURL, !servedURL.isEmpty { return servedURL }
    // National-team competitions only. `isInternationalSport` matches on the FULL
    // sport key ("soccer_fifa_world_cup"), so callers must pass the whole thing —
    // a truncated "soccer" both misses the World Cup and, if the guard were ever
    // dropped, would hang a country flag on Aston Villa.
    if isInternationalSport(sportKey), let flag = flagURL(for: teamName, width: 80) { return flag }
    return espnTeamLogoURL(for: teamName)
}

/// What a card should actually draw in an avatar slot.
enum TeamAvatarSlot: Sendable, Equatable {
    case image(url: URL, isPhotograph: Bool)
    /// No rung produced a url: the card draws its own coloured tile.
    case tile
}

/// Resolve one side's slot: the ladder, plus the one thing the ladder cannot know.
///
/// `isPhotograph` survives only for a **served** headshot. A url this ladder
/// derived is a crest or a flag, and cropping one of those square is exactly what
/// turned Zverev into a letterboxed sliver the first time faces landed (#2919) —
/// so a derived url is never a photograph, whatever the caller passed in.
func teamAvatarSlot(avatar: ParticipantAvatar, teamName: String, sportKey: String? = nil) -> TeamAvatarSlot {
    let served: String? = (avatar.url?.isEmpty == false) ? avatar.url : nil
    guard let resolved = teamAvatarURL(servedURL: served, teamName: teamName, sportKey: sportKey),
          let url = URL(string: resolved)
    else { return .tile }
    return .image(url: url, isPhotograph: served != nil && avatar.isPhotograph)
}
