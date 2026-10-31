import Foundation

/// #10868 — THE FOOTBALL SCREEN'S ROUTE CARD SETS: which card families each of
/// the six NFL routes shows, per phase.
///
/// PILLARS: DISCOVER / FORMATTING. SHIP: one football event screen serves every
/// NFL route, and each route shows exactly the stories its approved design
/// names — no route borrows another's cards, and none is dropped.
///
/// Pure data, transcribed from the route tracker's `card_groups`
/// (`shipping-adoption-20261027/route-tracker/tracker.json`, rows `nfl`,
/// `nfl-live`, `nfl-stories`, `nfl-team-stats`, `nfl-combined`, `nfl-replay`).
/// Every route lists the same groups in all three phases today; the phase
/// parameter keeps the map honest if the tracker ever splits them.
///
///   tracker words                                  family
///   ─────────────────────────────────────────────  ────────────────
///   "Player yardage / touchdowns / receptions"     `.playerMilestones`
///   "total and margin"                             `.totalAndMargin`
///   "team milestones", "Sacks and field goals"     `.teamMilestones`
///   "combined yards", "Combined ground + air       `.combinedYards`
///    yardage"
///
/// "team milestones" and "Sacks and field goals" are one family: the approved
/// `TeamMilestonesStory` is the team sacks and team field-goal pair, and the
/// accepted leaf for both is `PairedMilestonePresentation10868` (ab5c5d35).
///
/// The order is production's: the deck's fixed order (the projected finish,
/// then the player milestones — `NFLEventCardDeck9483.cards`), then the team
/// milestones, then combined yards. The tracker lists the groups, not an order.
///
/// ONE PHASE-SPECIFIC ADDITION (Design, 2026-10-31 review): the completed
/// `nfl-live` page also mounts the approved final period-winner story
/// (`FinalQuarterOutlooks` in the reference `Atlas.tsx`, mounted only on a
/// completed `nfl-live` and directly before the player stories). The tracker
/// omitted it; no other route and no pregame or live phase gains it. It sits
/// after the projected finish and immediately before the player milestones.
///
/// `nfl-replay` serves its card set at the reader's `now` in this pass. Its
/// replay mechanic — rebuilding every input as of a chosen instant and the
/// transport to move that instant — is not built here (`replayDependency`).
nonisolated enum FootballRoute10868: String, CaseIterable, Equatable, Sendable {
    case nfl = "nfl"
    case live = "nfl-live"
    case stories = "nfl-stories"
    case teamStats = "nfl-team-stats"
    case combined = "nfl-combined"
    case replay = "nfl-replay"
}

/// One kind of story a football route can show.
nonisolated enum FootballCardFamily10868: String, CaseIterable, Equatable, Sendable {
    /// Player yardage, touchdowns and receptions: the production player
    /// milestone cards (`NFLMilestoneCard9483`).
    case playerMilestones
    /// Total and margin: the production projected finish (`NFLFinishCard9483`)
    /// — the sportsbooks' projected final pair, and after the final the final
    /// against that forecast (`NFLFinalComparisonPresentation9483`).
    case totalAndMargin
    /// Team sacks and team field goals: `PairedMilestonePresentation10868`.
    case teamMilestones
    /// Combined rushing + receiving yards: the combined contract's milestone
    /// card beside `AdditiveStatSplitPresentation10868`.
    case combinedYards
    /// The final period winners: every regulation period's outcomes, each with
    /// its own pregame chance, the period's points and its own contract result
    /// (`FootballPeriodWinnersPresentation10868`). Completed `nfl-live` only.
    case periodWinners
}

nonisolated enum FootballRouteCardSet10868 {

    /// The families `route` shows in `phase`, in the screen's fixed order.
    static func families(_ route: FootballRoute10868,
                         phase: FootballEventPagePhase10868) -> [FootballCardFamily10868] {
        switch route {
        case .nfl, .stories, .replay:
            return [.totalAndMargin, .playerMilestones, .teamMilestones, .combinedYards]
        case .live:
            return phase == .final
                ? [.totalAndMargin, .periodWinners, .playerMilestones]
                : [.totalAndMargin, .playerMilestones]
        case .teamStats:
            return [.teamMilestones]
        case .combined:
            return [.combinedYards]
        }
    }

    /// The route a tracker id names, or nil for an id this screen does not serve.
    static func route(id: String) -> FootballRoute10868? {
        FootballRoute10868(rawValue: id)
    }

    /// Whether `route` shows `family` in `phase`.
    static func shows(_ family: FootballCardFamily10868, route: FootballRoute10868,
                      phase: FootballEventPagePhase10868) -> Bool {
        families(route, phase: phase).contains(family)
    }

    /// What `nfl-replay` still needs before it is more than its card set at
    /// `now`. Return/handoff words, never reader-facing.
    static let replayDependency =
        "nfl-replay: as-of rebuild of every input (headline, history, deck, team and combined cards) at a "
        + "chosen instant, plus the replay transport (PairedReplay.tsx) — owner: #10868 host / Native; "
        + "this pass serves the route's card set at the reader's now."
}
