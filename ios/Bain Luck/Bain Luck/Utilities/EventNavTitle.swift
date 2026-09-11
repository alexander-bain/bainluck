import Foundation

/// The event page's inline nav title, as a MODEL rather than one string.
///
/// #4900 — the title was built as a single string, `"{away} {as} - {home} {hs}
/// • {state}"`, and the title bar tail-truncates it. It always truncates the
/// END, which is where the second score is, so a reader who has scrolled the
/// hero off screen — the only time the title is the sole score on the page —
/// sees one team's number and not the other's. Photographed four times across
/// two sports:
///
///     BODO 0 - Munich...        15296763 UCL, actual 0 – 0
///     Sabah FK 0 - MAN...       15296764 UCL, actual 0 – 3
///     Rangers 0 - Marin...      15308638 MLB, actual 0 – 0
///     Al-Ittihad 2 - Al-Fa...   Saudi league, actual 2 – 1
///
/// WHY THIS IS A MODEL AND NOT A SHORTER STRING. The four specimens fit between
/// 16 and 24 characters in the same bar, because glyph widths differ — `BODO 0
/// - Munich 5 • FT 9…` rendered 24 characters where `Rangers 0 - Marin…` broke
/// at 17. So no character budget computed here can say whether a title fits;
/// only the layout can. This type hands the view the candidates, WIDEST FIRST,
/// and `ViewThatFits` picks. The last candidate is the one that must never
/// lose a number, so the view renders it as parts and protects the scores with
/// layout priority rather than trusting it to be short enough.
///
/// The two contributing causes named on the issue are both paid here without
/// either being fixed twice:
///
/// 1. **The trailing state is spent before the score is paid for.** It is the
///    first thing dropped. The MLB specimen isolates this: `Rangers 0 -
///    Mariners 0` fits with room, `• Bottom 2nd` is what pushes the away
///    number off. The hero owns the state, and the toolbar's live dot survives
///    the scroll.
/// 2. **Mixed designator register** (`BODO`/`Munich`, `Sabah FK`/`MAN`). The
///    compact candidate asks `TeamShortName.abbreviationPair` for the pair of
///    three-glyph codes — the SAME pair the crest badges draw. This is a
///    call-site choice, not a second implementation: whatever #4756 / #4624 /
///    #4627 land in that function arrives here for free, and nothing about
///    which glyphs a club draws is decided in this file.
enum EventNavTitle {

    /// One rendering of the title, in the order the bar should prefer them.
    struct Candidate: Equatable {
        let away: String
        let home: String
        let awayScore: String
        let homeScore: String
        /// Empty when this candidate has given up the state to buy width.
        let state: String

        /// The flat string, for the candidates the view renders as one `Text`
        /// and for tests that assert what a reader would read.
        var text: String {
            let line = "\(away) \(awayScore) - \(home) \(homeScore)"
            return state.isEmpty ? line : line + " • \(state)"
        }
    }

    /// The rungs of one title, widest first.
    ///
    /// Named rather than an array because `ViewThatFits` takes its children
    /// STATICALLY — a `ForEach` inside it is one child, not three, which would
    /// silently turn the whole ladder into a single candidate that always
    /// "fits". `ordered` exists for the tests, which do want the sequence.
    struct Rungs {
        /// Readable labels + state — what shipped, unchanged, for the titles
        /// that already fit (`BODO 0 - Munich 5 • FT`). Nil when there is no
        /// state, so the caller is never handed two identical rungs.
        let withState: Candidate?
        /// Readable labels, no state (`Rangers 0 - Mariners 0`).
        let labelled: Candidate
        /// Three-glyph codes, no state (`RAN 0 - MAR 0`) — the floor, and the
        /// only rung the view must render defensively.
        let compact: Candidate

        var ordered: [Candidate] {
            // The floor may repeat the rung above it — a served pair of
            // abbreviations is both the label and the code for plenty of teams
            // ("LAR", "SF"). Showing the same title twice costs nothing in the
            // view, but a test reading `ordered` should see the ladder that
            // actually exists.
            ([withState, labelled] + (compact == labelled ? [] : [compact])).compactMap { $0 }
        }
    }

    /// The title's rungs for a game with a score.
    static func rungs(
        away: String,
        home: String,
        awayScore: Int,
        homeScore: Int,
        awayServed: String? = nil,
        homeServed: String? = nil,
        state: String = ""
    ) -> Rungs {
        // #3430 — the two sides of ONE matchup, so the pair rule decides. Read
        // alone, "Tigers" names Clemson perfectly well; this title read
        // "Tigers 10 - Tigers 51" because LSU are the Tigers too.
        let labels = TeamShortName.shortPair(
            away: away, home: home, awayServed: awayServed, homeServed: homeServed
        )
        let codes = TeamShortName.abbreviationPair(
            away: away, home: home, awayServed: awayServed, homeServed: homeServed
        )
        let as_ = String(awayScore)
        let hs = String(homeScore)
        let trimmedState = state.trimmingCharacters(in: .whitespaces)

        return Rungs(
            withState: trimmedState.isEmpty ? nil : Candidate(
                away: labels.away, home: labels.home,
                awayScore: as_, homeScore: hs, state: trimmedState
            ),
            labelled: Candidate(away: labels.away, home: labels.home,
                                awayScore: as_, homeScore: hs, state: ""),
            compact: Candidate(away: codes.away, home: codes.home,
                               awayScore: as_, homeScore: hs, state: "")
        )
    }

    /// The pre-game title: no scores to protect, so there is nothing to choose.
    static func scoreless(
        away: String,
        home: String,
        awayServed: String? = nil,
        homeServed: String? = nil
    ) -> String {
        let labels = TeamShortName.shortPair(
            away: away, home: home, awayServed: awayServed, homeServed: homeServed
        )
        return "\(labels.away) vs \(labels.home)"
    }
}
