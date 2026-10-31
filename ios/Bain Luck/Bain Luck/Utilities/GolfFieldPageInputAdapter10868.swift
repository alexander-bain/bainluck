import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE
/// WHOLE PAGE INPUT.
///
/// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: the approved golf tournament
/// screen (`GolfEventPagePresentation10868`) can be fed from the futures bodies
/// the app already decodes — the Winner market, its history and any finish
/// markets the host holds — so its anchor, finish card, before-the-start
/// contenders card and golfer chooser arrive as one coherent screen for one
/// snapshot, one phase and one selected golfer.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, header, frames   part one (`GolfFieldPageAdapter10868`)
///   - readings, history       part two (`GolfFieldHistoryAdapter10868`); with no
///                             history response, only the chart slot says
///                             "History unavailable"
///   - finish outlook          part three (`GolfFieldFinishAdapter10868`), for the
///                             host's selected golfer only — none is elected here
///   - chooser, contenders     part four (`GolfFieldChooserAdapter10868`)
///
/// Every part reads ONE `Field` built here, so one golfer reads the same in the
/// chart key, the chooser card, the contenders bar and the Win slot.
///
/// Absent by design, named in the parts: the reading status (no golf hold
/// owner), the "What changed?" movement card (no tied pre-tournament pair owner)
/// and the finishing-position summary (no confirmed position source).
enum GolfFieldPageInputAdapter10868 {
    typealias Host = GolfFieldPageAdapter10868.Host

    /// The bodies the host already holds, passed in unchanged.
    struct Sources {
        /// `/api/futures/{id}` for the tournament's Winner market.
        let winner: FuturesMarketDetail
        /// `/api/futures/{id}/history` for the same market; nil when it has not
        /// arrived or failed (not claimed either way).
        let history: FuturesHistoryResponse?
        /// The finish markets the host holds, with its per-golfer join.
        let legs: GolfFieldFinishAdapter10868.Legs
        /// `GolfTournamentView`'s presentation, when the host holds it.
        let tournament: GolfTournamentPresentation?

        init(winner: FuturesMarketDetail, history: FuturesHistoryResponse?,
             legs: GolfFieldFinishAdapter10868.Legs = .init(), tournament: GolfTournamentPresentation? = nil) {
            self.winner = winner
            self.history = history
            self.legs = legs
            self.tournament = tournament
        }
    }

    /// The host's own reading state.
    struct Reading: Equatable {
        /// The chart's golfers (Winner outcome ids), in the host's order.
        var cohort: [Int]
        /// The host's selected golfer; nil shows the finish card's choose words.
        var selected: Int?
        /// The host's selected finish (recorded phase only).
        var selectedFinish: String?
        var chooser: GolfFieldChooserAdapter10868.Disclosures
        /// The reader's Full-scale choice; false is the approved Auto scale.
        var fullScale: Bool

        init(cohort: [Int], selected: Int? = nil, selectedFinish: String? = nil,
             chooser: GolfFieldChooserAdapter10868.Disclosures = .init(), fullScale: Bool = false) {
            self.cohort = cohort
            self.selected = selected
            self.selectedFinish = selectedFinish
            self.chooser = chooser
            self.fullScale = fullScale
        }
    }

    static func field(_ sources: Sources, now: Date) -> GolfFieldHistoryAdapter10868.Field {
        let winner = sources.winner
        return GolfFieldHistoryAdapter10868.Field(
            market: winner, history: sources.history,
            phase: GolfFieldPageAdapter10868.phase(winner, now: now),
            listedStart: GolfFieldPageAdapter10868.listedStart(winner),
            now: now)
    }

    static func input(_ sources: Sources, reading: Reading, chooserAvailable: Bool = true,
                      host: Host) -> GolfEventPageInput10868 {
        let field = self.field(sources, now: host.now)
        let winner = sources.winner
        let history: FieldHistoryInput10868 = sources.history == nil
            ? GolfFieldHistoryAdapter10868.unavailable(winner, cohort: reading.cohort, selected: reading.selected,
                                                       phase: field.phase, chooserAvailable: chooserAvailable)
            : GolfFieldHistoryAdapter10868.history(field, cohort: reading.cohort, selected: reading.selected,
                                                   chooserAvailable: chooserAvailable, full: reading.fullScale, host: host)
        let chooser = GolfFieldChooserAdapter10868.chooser(field, cohort: reading.cohort, selected: reading.selected,
                                                           state: reading.chooser, host: host)
        let finish: GolfFinishExpectationInput10868? = reading.selected.flatMap {
            GolfFieldFinishAdapter10868.finish(field, golfer: $0, legs: sources.legs,
                                               tint: tint(field, cohort: reading.cohort, golfer: $0),
                                               selectedFinish: reading.selectedFinish, host: host)
        }
        let unavailableWords = reading.selected == nil
            ? GolfFieldPageAdapter10868.Words.chooseGolfer
            : GolfFieldPageAdapter10868.Words.finishUnavailable
        return GolfEventPageInput10868(
            phase: field.phase,
            copy: GolfFieldPageAdapter10868.copy(winner, tournament: sources.tournament, phase: field.phase,
                                                 finishUnavailable: unavailableWords, host: host),
            status: nil,
            history: history,
            finish: finish,
            finishFrame: GolfFieldPageAdapter10868.finishFrame(winner, phase: field.phase),
            contenders: GolfFieldChooserAdapter10868.contenders(field, chooser: chooser, cohort: reading.cohort, host: host),
            contendersFrame: GolfFieldPageAdapter10868.contendersFrame(),
            movement: nil,
            movementFrame: GolfFieldPageAdapter10868.movementFrame(),
            chooser: chooserAvailable ? chooser : nil)
    }

    /// The golfer's chart tint, so the finish bars match their line; the app's
    /// accent when the golfer is not drawn.
    static func tint(_ field: GolfFieldHistoryAdapter10868.Field, cohort: [Int], golfer: Int) -> Color {
        let drawn = GolfFieldHistoryAdapter10868.drawnGolfers(field, cohort: cohort)
        guard let position = drawn.firstIndex(where: { $0.id == golfer }) else { return DS.blue }
        return GolfFieldHistoryAdapter10868.tint(position)
    }
}
