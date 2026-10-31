import SwiftUI

/// #10868 — THE TENNIS MATCH SCREEN'S CARD ADMISSION: how an owner's story
/// cards reach the page, and how their taps reach Details.
///
/// PILLARS: MATCHING / FORMATTING / DISCOVER. SHIP: when an owner supplies a
/// proved tennis story card — first-set or set-winner panels, total games,
/// exact set finishes, set and game handicaps — the event page mounts it in the
/// phase it belongs to, offers it in the story stream and the full-size reader,
/// keeps the reader's held choice on it, and its Details opens exactly that
/// original in All props, never a neighbour.
///
/// NO PRODUCTION OWNER SUPPLIES A TENNIS CARD TODAY (`TennisPageInputAdapter10868`
/// names why: the served matrix types no tennis question, `EventDetail` does
/// not decode `linescore`, settled tennis options serve no pin). The proposed
/// mount passes nil, so the page is unchanged. This file is the path an owner's
/// admitted data takes once it exists; it decides nothing about markets.
///
/// What an owner supplies (`Supplied`), all typed, all optional:
///   - the event it built the cards for (`eventID`) — another event's page
///     admits none of them;
///   - the accepted leaves' own input contracts, built by that owner from
///     decoded models: `PeriodOutcomeFinalScoreInput10868`,
///     `TennisEventPageTotals10868`, `TennisEventPageExact10868`;
///   - for handicaps, only the owner-proved panel words, actuals and exact
///     catalogue identities (`Handicaps`) — the page attaches its own catalogue,
///     its held selection and its phase, so a panel's chance and result are
///     always the page's own Details (`OriginalHandicapCard9483`);
///   - the exact catalogue identity each leaf original id opens (`Routes`), as
///     that owner proved it. No route is inferred from a label, an id's shape
///     or a position.
///
/// What the host owns (`Held`): the reader's chosen milestone on the totals card
/// and chosen finish on the final's exact card, applied over the owner's input
/// through the leaves' own selection fields. Nil keeps the owner's selection.
///
/// Which supplied card is offered at all is the page's own mount rule
/// (`TennisEventPageModel10868`), applied in `TennisPageInputAdapter10868`: a
/// card in the wrong phase, the wrong variant or with nothing to show is never
/// offered. Nothing here fetches, subscribes, formats a figure, grades or ranks.
enum TennisCardsAdapter10868 {
    typealias Details = OriginalMarketDetails9483

    /// The owner's handicap card without the page's catalogue, held selection
    /// and phase, which the page attaches.
    struct Handicaps: Equatable {
        /// Panels in the owner's order, each naming one exact catalogue original.
        let groups: [OriginalHandicapCard9483.Group]
        let words: OriginalHandicapCard9483.Words
        var showsDuringPlay: Bool = false
        var showsBeforePlay: Bool = false
    }

    /// The exact catalogue original each leaf original id opens, per card.
    struct Routes: Equatable {
        /// `PeriodOutcomeFinalScorePresentation10868`'s details ids.
        var sets: [String: Details.Identity] = [:]
        /// The totals card's milestone ids.
        var totals: [String: Details.Identity] = [:]
        /// The exact card's original ids, inside its own scope.
        var exact: [String: Details.Identity] = [:]

        init(sets: [String: Details.Identity] = [:], totals: [String: Details.Identity] = [:],
             exact: [String: Details.Identity] = [:]) {
            self.sets = sets
            self.totals = totals
            self.exact = exact
        }
    }

    /// Everything an owner admits for one event's cards.
    struct Supplied: Equatable {
        /// The event these cards were built for.
        let eventID: Int
        var sets: PeriodOutcomeFinalScoreInput10868? = nil
        var totals: TennisEventPageTotals10868? = nil
        var exact: TennisEventPageExact10868? = nil
        var handicaps: Handicaps? = nil
        var routes = Routes()
    }

    /// The reader's own choices on the cards, held by the host.
    struct Held: Equatable {
        var totalMilestoneID: String? = nil
        var exactScopeID: String? = nil
        var exactOriginalID: String? = nil

        init(totalMilestoneID: String? = nil, exactScopeID: String? = nil, exactOriginalID: String? = nil) {
            self.totalMilestoneID = totalMilestoneID
            self.exactScopeID = exactScopeID
            self.exactOriginalID = exactOriginalID
        }
    }

    /// The four page inputs, before the page's own mount rule.
    struct Admitted: Equatable {
        var sets: PeriodOutcomeFinalScoreInput10868? = nil
        var totals: TennisEventPageTotals10868? = nil
        var exact: TennisEventPageExact10868? = nil
        var handicaps: TennisEventPageHandicaps10868? = nil
    }

    // MARK: - Admission

    /// The supplied cards for THIS event, with the page's catalogue, held
    /// selection and phase on the handicaps and the host's held choices on the
    /// totals and exact cards. Nothing supplied, or supplied for another event,
    /// admits nothing.
    static func admit(_ supplied: Supplied?, event: EventDetail, phase: TennisEventPagePhase10868,
                      originals: TennisEventPageOriginals10868, held: Held, tint: Color) -> Admitted {
        guard let supplied, supplied.eventID == event.id else { return Admitted() }
        return Admitted(
            sets: supplied.sets,
            totals: supplied.totals.map { holding($0, milestone: held.totalMilestoneID) },
            exact: supplied.exact.map { holding($0, scope: held.exactScopeID, original: held.exactOriginalID) },
            handicaps: supplied.handicaps.map {
                TennisEventPageHandicaps10868(
                    input: OriginalHandicapCard9483.Input(
                        phase: TennisEventPageModel10868.handicapPhase(phase), catalogue: originals.catalogue,
                        held: originals.selection, groups: $0.groups, words: $0.words,
                        showsDuringPlay: $0.showsDuringPlay, showsBeforePlay: $0.showsBeforePlay),
                    tint: tint)
            })
    }

    /// The totals card with the host's held milestone, or the owner's own
    /// selection when the host holds none. The leaf resolves a held id that is
    /// no longer offered as missing, never as a neighbour.
    static func holding(_ totals: TennisEventPageTotals10868, milestone: String?) -> TennisEventPageTotals10868 {
        guard let milestone else { return totals }
        switch totals {
        case .final(let line):
            return .final(TotalMilestoneLineComparisonInput10868(
                profile: holding(line.profile, milestone: milestone), openingLine: line.openingLine,
                difference: line.difference, quantitiesShareUnit: line.quantitiesShareUnit,
                originalsTitle: line.originalsTitle, invitation: line.invitation))
        case .thresholds(let live):
            return .thresholds(TotalMilestoneThresholdLiveInput10868(
                profile: holding(live.profile, milestone: milestone), thresholds: live.thresholds,
                subtotals: live.subtotals, quantitiesShareUnit: live.quantitiesShareUnit, words: live.words,
                beforePresentation: live.beforePresentation))
        }
    }

    static func holding(_ profile: TotalMilestoneInput10868, milestone: String) -> TotalMilestoneInput10868 {
        TotalMilestoneInput10868(
            phase: profile.phase, eyebrow: profile.eyebrow, title: profile.title, chartTitle: profile.chartTitle,
            quantityAxisTitle: profile.quantityAxisTitle, milestones: profile.milestones,
            selectedMilestoneID: milestone, actual: profile.actual, projection: profile.projection,
            quantityDomain: profile.quantityDomain, quantityTicks: profile.quantityTicks,
            chanceTicks: profile.chanceTicks, timing: profile.timing, markStyle: profile.markStyle)
    }

    /// The final's finish tiles with the host's held finish. The lanes have no
    /// selection of their own and pass through unchanged.
    static func holding(_ exact: TennisEventPageExact10868, scope: String?, original: String?) -> TennisEventPageExact10868 {
        guard case .final(let tiles) = exact, let scope, let original else { return exact }
        let map = tiles.map
        return .final(ExactScoreFinishInput10868(
            map: ExactScoreMapInput10868(
                phase: map.phase, title: map.title, intro: map.intro, homeLabel: map.homeLabel,
                awayLabel: map.awayLabel, rowsTitle: map.rowsTitle, columnsTitle: map.columnsTitle,
                scopes: map.scopes, selectedScopeID: scope, selectedOriginalID: original,
                legend: map.legend, words: map.words),
            players: tiles.players, words: tiles.words))
    }

    // MARK: - Details

    /// The catalogue selection an owner route names: exactly one catalogue
    /// original with that identity, in the catalogue's own scope. Else nil.
    static func selection(_ identity: Details.Identity?,
                          in originals: TennisEventPageOriginals10868) -> Details.Selection? {
        guard let identity, let catalogue = originals.catalogue,
              catalogue.originals.filter({ $0.identity == identity }).count == 1 else { return nil }
        return Details.Selection(scope: catalogue.scope, identity: identity)
    }

    /// A set panel's Details.
    static func setDetails(_ id: String, supplied: Supplied?,
                           originals: TennisEventPageOriginals10868) -> Details.Selection? {
        selection(supplied?.routes.sets[id], in: originals)
    }

    /// A totals milestone's Details.
    static func totalDetails(_ id: String, supplied: Supplied?,
                             originals: TennisEventPageOriginals10868) -> Details.Selection? {
        selection(supplied?.routes.totals[id], in: originals)
    }

    /// An exact finish's Details: only inside the mounted card's own scope.
    static func exactDetails(scopeID: String, originalID: String, mounted: TennisEventPageExact10868?,
                             supplied: Supplied?, originals: TennisEventPageOriginals10868) -> Details.Selection? {
        guard let scope = exactScopeID(mounted), scope == scopeID else { return nil }
        return selection(supplied?.routes.exact[originalID], in: originals)
    }

    /// A handicap panel's own selection, admitted only when it names one
    /// original of the page's own catalogue.
    static func handicapSelection(_ chosen: Details.Selection,
                                  in originals: TennisEventPageOriginals10868) -> Details.Selection? {
        guard let catalogue = originals.catalogue, chosen.scope == catalogue.scope,
              Details.original(in: catalogue, selection: chosen) != nil else { return nil }
        return chosen
    }

    /// The exact card's own scope id, whichever variant is mounted.
    static func exactScopeID(_ exact: TennisEventPageExact10868?) -> String? {
        switch exact {
        case .final(let tiles)?: tiles.scope?.id
        case .lanes(let lanes)?: lanes.scope?.id
        case nil: nil
        }
    }
}
