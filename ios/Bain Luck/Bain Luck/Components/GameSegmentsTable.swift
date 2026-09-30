import SwiftUI

/// The grid of the Game Segments card: a header of period labels, one row per
/// competitor, and the scoreboard's total at the end of each row.
///
/// #4089 — LIFTED OUT OF `GameSegmentsView` SO THE TOTAL COLUMN CAN BE PINNED, and
/// so a test can point a camera at the layout it picks.
///
/// UX-P090 tuned the geometry so a nine-inning table fits a 375pt SE at the
/// DEFAULT text size, and wrapped it in a horizontal scroll view for anything
/// wider. At the accessibility sizes every column grows with its ink and the row
/// passes the right edge — and because the scroll view held the whole row, the
/// thing that went off screen first was `T`, the one column this card exists to
/// reconcile against the hero score. Athletics 6 – Mariners 2 (`15304933`) at
/// accessibility-extra-large on a 402pt iPhone 17 drew innings 1–9 and cut the
/// totals.
///
/// So there are two layouts, and SwiftUI picks between them by measuring:
///
/// 1. **The whole table, when it fits** — exactly what UX-P090 shipped, which is
///    every table at the default text size. Nothing about Alex's accepted layout
///    moves.
/// 2. **Otherwise, names and totals pinned, periods scrolling between them.** The
///    reader always sees whose row it is and what it adds up to; the innings are
///    the part that scrolls, with the indicator on so the overflow announces
///    itself (UX-P090's reason for turning it on still holds).
///
/// The pinned layout is three grids side by side, so their rows must stay the
/// same height or the columns shear vertically. Every cell in a row uses the same
/// text style — `caption2` across the header, `caption` down each team row — and
/// the header's corner cell is a hidden copy of the `T` label rather than an empty
/// string, so the three grids resolve the same row heights at every text size.
struct GameSegmentsTable: View {
    let columns: [LineScoreColumn]
    let awayBadge: String
    let homeBadge: String
    let awayColor: Color
    let homeColor: Color
    let awayTotal: Int
    let homeTotal: Int

    /// Which slice of the table a grid draws. `.all` is the one-grid layout.
    enum Part {
        case all, teams, periods, totals
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            grid(.all)
            HStack(alignment: .top, spacing: Self.columnSpacing) {
                grid(.teams)
                ScrollView(.horizontal, showsIndicators: true) {
                    grid(.periods)
                }
                grid(.totals)
            }
        }
    }

    /// UX-P090's 4pt gap, used between the grids of the pinned layout too so the
    /// two layouts space their columns alike.
    static let columnSpacing: CGFloat = 4

    /// Internal, not private, so a test can check the three pinned grids draw
    /// at the same height.
    func grid(_ part: Part) -> some View {
        let showsTeams = part == .all || part == .teams
        let showsPeriods = part == .all || part == .periods
        let showsTotals = part == .all || part == .totals
        return Grid(alignment: .trailing, horizontalSpacing: Self.columnSpacing, verticalSpacing: 8) {
            GridRow {
                if showsTeams {
                    // #3977 — the corner above the team badges carries the same
                    // floor as the badge and declares the column leading-aligned,
                    // so two badges of unequal ink still start their dots at the
                    // same x. #4089 — a hidden `T`, not `""`, so it is exactly as
                    // tall as the header cells in the other grids.
                    totalHeader
                        .hidden()
                        .frame(
                            minWidth: GameSegmentTeamBadge.minimumWidthPoints,
                            alignment: .leading)
                        .gridColumnAlignment(.leading)
                        .accessibilityHidden(true)
                }
                if showsPeriods {
                    ForEach(Array(columns.enumerated()), id: \.offset) { _, column in
                        Text(column.label)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .frame(minWidth: 22)
                    }
                }
                if showsTotals {
                    totalHeader
                }
            }

            row(
                team: awayBadge, color: awayColor,
                cells: columns.map(\.away), total: awayTotal,
                showsTeams: showsTeams, showsPeriods: showsPeriods, showsTotals: showsTotals)
            row(
                team: homeBadge, color: homeColor,
                cells: columns.map(\.home), total: homeTotal,
                showsTeams: showsTeams, showsPeriods: showsPeriods, showsTotals: showsTotals)
        }
        .padding(.vertical, 2)
    }

    private var totalHeader: some View {
        Text("T")
            .font(.caption2.weight(.bold))
            .foregroundStyle(.primary)
            .frame(minWidth: 26)
            // A hairline gutter so the total reads as a separate quantity from
            // the last inning rather than a 10th.
            .padding(.leading, 6)
    }

    private func row(
        team: String, color: Color, cells: [LineScoreCell], total: Int,
        showsTeams: Bool, showsPeriods: Bool, showsTotals: Bool
    ) -> some View {
        GridRow {
            if showsTeams {
                // UX-P090: the header's corner cell and this badge must move
                // together or the columns shear — #3977 put both on one floor.
                GameSegmentTeamBadge(team: team, color: color)
            }
            if showsPeriods {
                ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                    // `·` for an inning we never observed. Printing `0` there
                    // would assert nobody scored, which we do not know (#1831).
                    // A period still to come is blank and baseball's unneeded
                    // half is `X` (#9067) — neither is a gap, so neither is
                    // dimmed as one.
                    Text(cell.text)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(cell == .unknown ? .tertiary : .secondary)
                        .frame(minWidth: 22)
                }
            }
            if showsTotals {
                Text("\(total)")
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(.primary)
                    .frame(minWidth: 26)
                    .padding(.leading, 6)
            }
        }
    }
}
