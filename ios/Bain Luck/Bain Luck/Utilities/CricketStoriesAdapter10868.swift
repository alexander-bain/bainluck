import Foundation

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE
/// STORIES PRODUCTION DATA CAN FEED, AND THE ONES IT CANNOT.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `cricket-live` a reader sees how each
/// original's chance moved from pregame during play ("Changing expectations")
/// and, at the final, each original's pregame chance beside the reported result
/// ("Expectations and result") — and no chase or holding-on card is ever drawn
/// with runs, wickets or overs the app does not have.
///
/// Both cards are built from part one's headline rows, unchanged: the same
/// readings, figures, provenance, shapes and tints, so the headline and its
/// stories can never disagree about one original. This file decides only
/// whether a card has anything to compare.
///
///   - Changing expectations  during play only, comparison mode, and only when
///                            at least one original shows BOTH its pregame and
///                            its in-play figure — otherwise there is no change
///                            to show and the headline already says why. No
///                            point change is written: no production authority
///                            states a pregame→in-play movement for an original,
///                            and `deltaPointsNumber` formats a magnitude whose
///                            unit word is an open copy decision (#6931). The
///                            card's two marks and connector carry the change;
///                            the movement line stays nil (named dependency).
///   - Expectations and       at the final only, completed mode, when an
///     result                 original shows a pregame figure or a reported
///                            result. Its grade slot is absent: the headline's
///                            pair is the page's blend, not an original contract
///                            (each original's grade is in its Details, part
///                            three).
///
/// NEVER BUILT, EACH FOR A NAMED REASON:
///   - The chase              needs the batting side's innings runs, the win
///                            target, wickets and overs with their report clock.
///                            No production model carries any of them: cricket
///                            `homeScore` / `awayScore` are whole numbers, null on
///                            every retained cricket body, and the backend notes
///                            nothing observes cricket scores (event_completion.py
///                            "cricket … fewer than five completed rows carrying
///                            a score in 21 days").
///   - Holding on             needs per-checkpoint wicket reports and the draw /
///                            tie original's own separately timed chance; neither
///                            reaches the app (part one: no draw price decoded).
enum CricketStoriesAdapter10868 {
    typealias Page = CricketEventPageAdapter10868

    enum Words {
        static let shiftsEyebrowCurrent = "Pregame → current chance"
        static let shiftsEyebrowRecorded = "Pregame → last recorded chance"
        static let shiftsTitle = "How the outlook changed"
        static let expectationsEyebrow = "Pregame expectations → result"
        static let independentNote = "Each chance is its own reading; they are not adjusted to add up to 100%."
        /// The reference's note (`CricketLifecycle.tsx` Expectations), in this app's words.
        static let expectationsNote = "Hollow marks are pregame chances. Result labels describe the match, not later chances."
        static let gradeLabel = "Original contract"
    }

    /// Changing expectations: during play, in comparison mode, when some
    /// original shows both readings. Otherwise nil, and the card is not offered.
    static func shifts(_ headline: CricketHeadlineInput10868) -> CricketOutlookInput10868? {
        guard headline.phase == .during,
              headline.rows.contains(where: { $0.before.observation != nil && $0.comparison.observation != nil })
        else { return nil }
        let eyebrow = headline.comparisonLabel == Page.Words.lastRecorded
            ? Words.shiftsEyebrowRecorded : Words.shiftsEyebrowCurrent
        return CricketOutlookInput10868(
            eyebrow: eyebrow,
            title: Words.shiftsTitle,
            beforeLabel: headline.beforeLabel,
            comparisonLabel: headline.comparisonLabel,
            rows: headline.rows,
            selectedRowID: nil,
            notes: [Words.independentNote],
            mode: .comparison)
    }

    /// Expectations and result: at the final, in completed mode, when some
    /// original shows a pregame figure or a reported result.
    static func expectations(_ headline: CricketHeadlineInput10868) -> CricketOutlookInput10868? {
        guard headline.phase == .completed,
              headline.rows.contains(where: { $0.before.observation != nil || $0.finish?.outcome.word != nil })
        else { return nil }
        let frame = CricketOutlookFinalFrame10868(
            outcomeLabel: headline.outcomeLabel,
            outcomeMissing: headline.outcomeMissing,
            gradeLabel: Words.gradeLabel,
            context: [])
        return CricketOutlookInput10868(
            eyebrow: Words.expectationsEyebrow,
            title: nil,
            beforeLabel: headline.beforeLabel,
            comparisonLabel: headline.comparisonLabel,
            rows: headline.rows,
            selectedRowID: nil,
            notes: [Words.expectationsNote],
            mode: .completed(frame))
    }
}
