import SwiftUI

// MARK: - Ladder primitive (QuantityGroup analogue)
//
// One question, many milestones/thresholds, one card. This is the native port of
// the web `QuantityGroup` "ladder-strip" kernel and the adopted "2b" design from the
// Native Championship Grids handoff (docs/archive/designs/.../Native Championship Grids.dc.html,
// Turn 3: "2b adopted as the ladder component").
//
// It is now the ONE ladder component everywhere (kernel discipline): the feed's
// grouped playoff progression (via `LadderRung(stage:)`) and the league screen's
// ranked per-team list (design 2c, via `LadderCardView(gridTeam:columns:)`) both
// render on it; the compact `ProgressionLadderView` was retired in L2-123.
// Championship milestones and prop thresholds are the same shape — "one component,
// two label modes" (design note 1g).

/// Settlement state of a single ladder rung. Drives the "settled chrome" (design 1f):
/// clinched fills deep ink with a ✓ and drops the numeral; eliminated greys out with
/// a ✕; a live-but-implied 100% keeps its numeral because the market can still move.
nonisolated enum LadderRungState: String, Sendable {
    case open        // live, still trading
    case clinched    // official — outcome achieved
    case eliminated  // official — outcome impossible
}

/// A single row in a ladder card: a milestone ("WORLD SERIES") or a prop threshold ("50+").
nonisolated struct LadderRung: Identifiable, Sendable {
    let id: String
    let label: String
    let probability: Double?   // 0.0–1.0, nil when unknown
    var state: LadderRungState

    init(id: String, label: String, probability: Double?, state: LadderRungState = .open) {
        self.id = id
        self.label = label
        self.probability = probability
        self.state = state
    }
}

/// #7036, fourth arm — the ladder card's badge colour, resolved through the
/// contrast floor.
///
/// The colour this card is handed is drawn as LETTERS in both of the badge's
/// branches — as the initials themselves when a crest exists but cannot be
/// fetched (`TeamLogoView.initialsFallback` paints `Text(...).foregroundStyle(color)`),
/// and as the fill under `Text(abbr).foregroundStyle(.white)` when there is no
/// crest url at all. For the 146 clubs whose stored `primary_color` is under 3:1
/// against a white card, both branches produce a blank circle.
///
/// **How reachable, measured 2026-09-20 and not inferred from the branches.**
/// The second branch is currently dead for this defect: on `/api/playoffs/epl`,
/// `la-liga` and `bundesliga` every logo-less row (Coventry, Hull, Atletico
/// Madrid, Alaves, Deportivo, Malaga, Racing Santander, M´gladbach, Mainz 05)
/// serves `primary_color: null` and therefore already takes the default, while
/// every white-shirted row serves a crest that returns 200. The first branch is
/// the live one and it is a FAILURE path — a dead CDN, an offline phone, a load
/// that loses its race. So this makes the app's fallback legible rather than
/// repairing a card a reader is looking at right now, and anyone quoting it
/// should quote it that way.
///
/// `DS.emeraldDark` (`#059669`, 3.77:1) is the card's OWN existing default — the
/// value a team with no stored colour already gets — so this is a floor under
/// current behaviour rather than a new palette. Exposed as a hex because a
/// `Color` cannot be compared in a test, and the mutant worth killing is a call
/// site that has quietly gone back to `Color(hex: team.primaryColor)`.
///
/// 🪤 **One honest discrepancy, stated rather than papered over.**
/// `DS.emeraldDark` is spelled `Color(red: 0.02, green: 0.59, blue: 0.40)` and
/// annotated `// #059669`; those are not the same value — the literal renders
/// (5, 150, **102**) and the comment says (5, 150, **105**). This takes the
/// annotated hex, so a *floored* club's badge is 3/255 of blue away from the
/// badge of a club that never had a colour at all. That is below any reader's
/// threshold and both clear the floor, and the alternative — redefining
/// `DS.emeraldDark` from a hex — repaints every other surface that uses it for
/// a change nobody asked for. Named here so the next person finds it stated
/// instead of measuring it.
enum LadderCardTeamColour {
    static let fallbackHex = "#059669"

    static func badgeHex(_ storedHex: String?) -> String {
        TeamTextContrast.textHexOnCard(storedHex, fallback: fallbackHex)
    }
}

// MARK: - LadderCardView

/// The adopted "2b" bar-ladder card: a team/entity header with a per-rung labeled
/// bar (length = probability) and an optional headline 24h delta. Renders settled
/// chrome per rung and mutes the whole card when the entity is eliminated.
struct LadderCardView: View {
    let title: String
    var abbr: String? = nil
    var logoUrl: String? = nil
    var teamColor: Color = DS.emeraldDark
    var rank: Int? = nil
    var subtitle: String? = nil        // e.g. record "51-40"
    let rungs: [LadderRung]

    /// Headline delta shown on the right of the header (e.g. the WS 24h move, in points).
    var headlineDeltaLabel: String? = nil   // e.g. "WIN 24H"
    var headlineDelta: Double? = nil         // in percentage points, e.g. -2.2

    var clinched: Bool = false
    var eliminated: Bool = false

    /// Width of the milestone-label column. Uniform milestones (PLAYOFFS/…/WORLD SERIES)
    /// use the default; short prop thresholds ("50+") can pass a narrower width.
    var labelWidth: CGFloat = 82
    var onRungTap: ((LadderRung) -> Void)? = nil

    // Design tokens (match the handoff palette exactly)
    private let heat = DS.emeraldDark          // #059669 live fill
    private let settledInk = Color(hex: "#065F46")  // clinched deep ink
    private let track = Color(hex: "#EEF0F3")       // bar track

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            VStack(spacing: 6) {
                ForEach(rungs) { rung in
                    rungRow(rung)
                }
            }
        }
        .padding(12)
        .background(DS.cardBg)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(DS.border, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .shadow(color: Color.black.opacity(0.06), radius: 3, x: 0, y: 1)
        .opacity(eliminated ? 0.75 : 1.0)
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 8) {
            if let rank {
                Text("\(rank)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(DS.textMuted)
                    .frame(width: 18, alignment: .leading)
            }

            badge

            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(eliminated ? DS.textSecondary : DS.textPrimary)
                .lineLimit(1)

            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundStyle(DS.textMuted)
                    .lineLimit(1)
            }

            if clinched {
                statusPill(text: "CLINCHED ✓", fg: settledInk, bg: settledInk.opacity(0.1))
            } else if eliminated {
                statusPill(text: "ELIMINATED", fg: DS.textMuted, bg: DS.trackBg)
            }

            Spacer(minLength: 4)

            if let headlineDelta, !clinched && !eliminated {
                headerDelta(headlineDelta)
            }
        }
    }

    @ViewBuilder
    private var badge: some View {
        if let logoUrl, !logoUrl.isEmpty {
            TeamLogoView(url: logoUrl, teamName: title, color: teamColor, size: 24)
        } else if let abbr {
            Text(abbr)
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 24, height: 24)
                .background(Circle().fill(teamColor))
        }
    }

    private func headerDelta(_ delta: Double) -> some View {
        HStack(spacing: 4) {
            if let headlineDeltaLabel {
                Text(headlineDeltaLabel)
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(0.4)
                    .foregroundStyle(DS.textMuted)
            }
            deltaValue(delta)
        }
    }

    // MARK: Rung row (labeled bar — design 2b)

    private func rungRow(_ rung: LadderRung) -> some View {
        let content = HStack(spacing: 8) {
            Text(rung.label)
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.4)
                .foregroundStyle(DS.textSecondary)
                .lineLimit(1)
                .frame(width: labelWidth, alignment: .leading)

            bar(for: rung)

            trailingValue(for: rung)
                .frame(width: 44, alignment: .trailing)
        }
        .contentShape(Rectangle())

        return Group {
            if let onRungTap {
                Button { onRungTap(rung) } label: { content }
                    .buttonStyle(.plain)
            } else {
                content
            }
        }
    }

    private func bar(for rung: LadderRung) -> some View {
        let prob = max(0, min(1, rung.probability ?? 0))
        let (fill, width): (Color, Double) = {
            switch rung.state {
            case .clinched:   return (settledInk, 1.0)
            case .eliminated: return (.clear, 0.0)
            case .open:       return (heat, prob)
            }
        }()
        return GeometryReader { geo in
            Capsule()
                .fill(track)
                .frame(height: 8)
                .overlay(alignment: .leading) {
                    Capsule()
                        .fill(fill)
                        .frame(width: geo.size.width * width, height: 8)
                }
        }
        .frame(height: 8)
    }

    @ViewBuilder
    private func trailingValue(for rung: LadderRung) -> some View {
        switch rung.state {
        case .clinched:
            Text("✓")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(settledInk)
        case .eliminated:
            Text("✕")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(DS.textMuted)
        case .open:
            Text(ladderPercent(rung.probability))
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundStyle(DS.textPrimary)
        }
    }

    // MARK: Small pieces

    private func statusPill(text: String, fg: Color, bg: Color) -> some View {
        Text(text)
            .font(.system(size: 9, weight: .semibold))
            .tracking(0.4)
            .foregroundStyle(fg)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(RoundedRectangle(cornerRadius: 6).fill(bg))
    }

    private func deltaValue(_ delta: Double) -> some View {
        // Muted em-dash when the move is negligible (design: quiet rows stay quiet).
        Group {
            if abs(delta) < 0.05 {
                Text("—")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(DS.textMuted.opacity(0.6))
            } else {
                HStack(spacing: 2) {
                    Image(systemName: delta > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 8, weight: .bold))
                    Text(String(format: "%.1f", abs(delta)))
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                .foregroundStyle(delta > 0 ? DS.kalshiGreen : DS.danger)
            }
        }
    }
}

// MARK: - Percentage formatting (design `fmt`: round ≥10%, one decimal below)

/// Formats a 0.0–1.0 probability the way the ladder design does: whole percent at or
/// above 10% ("78%"), one decimal below ("6.9%", "0.4%"). Distinct from the app-wide
/// `formatProbability`, which clamps to "<1%"/">99%".
func ladderPercent(_ value: Double?) -> String {
    guard let value else { return "—" }
    let pct = value * 100
    if pct >= 10 { return "\(Int(pct.rounded()))%" }
    if pct <= 0 { return "0%" }
    return String(format: "%.1f%%", pct)
}

// MARK: - Adapters from existing models (fold-in, not greenfield)

extension LadderRung {
    /// Build from a feed `ProgressionStage` (achieved → clinched, eliminated → eliminated).
    init(stage: ProgressionStage) {
        let state: LadderRungState
        switch stage.status {
        case "achieved":   state = .clinched
        case "eliminated": state = .eliminated
        default:           state = .open
        }
        self.init(id: "\(stage.id)", label: stage.label, probability: stage.probability, state: state)
    }
}

extension LadderRungState {
    /// #7557 — the grid cell's declared state, mapped onto the rung's settled chrome.
    ///
    /// `missing` and `unavailable` are `.open`, which is the branch that prints
    /// the honest "—". They are deliberately NOT `.clinched`/`.eliminated`:
    /// those publish a verdict, and "we have no market" is not a verdict.
    init(gridCell state: GridCellRenderState) {
        switch state {
        case .won:                          self = .clinched
        case .eliminated:                   self = .eliminated
        case .live, .missing, .unavailable: self = .open
        }
    }
}

extension LadderCardView {
    /// Build a per-team ladder card from the championship-grid models
    /// (`GridTeam` + ordered `[GridColumn]`). The last column's 24h trend becomes the
    /// headline delta ("WIN 24H"), matching the design's per-card delta.
    ///
    /// #7557: every cell is read through `renderState` / `publishedProbability`,
    /// never through `mergedProbability` raw — a graded cell hands this adapter a
    /// RESULT and no number, and reading the number alone is what printed the
    /// no-market "—" on 53 decided MLB cells.
    init(gridTeam team: GridTeam, columns: [GridColumn], rank: Int? = nil) {
        let ordered = columns.sorted { $0.order < $1.order }
        let rungs = ordered.map { col -> LadderRung in
            let cell = team.cells[col.key]
            // A column with no cell at all is `missing`, which renders exactly
            // as it did before: an open rung with no number.
            let state = cell?.renderState ?? .missing
            return LadderRung(
                id: col.key,
                label: col.label,
                probability: cell?.publishedProbability,
                state: LadderRungState(gridCell: state)
            )
        }
        let lastKey = ordered.last?.key
        let lastLabel = ordered.last?.label
        let trend = lastKey.flatMap { team.cells[$0]?.publishedTrend24H }

        self.init(
            title: team.name,
            abbr: team.shortName,
            logoUrl: team.logoUrl,
            teamColor: Color(hex: LadderCardTeamColour.badgeHex(team.primaryColor)),
            rank: rank ?? team.seed,
            subtitle: team.record,
            rungs: rungs,
            headlineDeltaLabel: lastLabel.map { shortDeltaLabel(key: lastKey, label: $0) },
            headlineDelta: trend.map { $0 * 100 }
        )
    }
}

/// The compact header tag naming the rung a ladder card's 24h delta belongs to
/// ("WIN 24H"). Keyed on the grid column's stable `key`, never on its display label.
///
/// #4838: this was keyed on `label.uppercased()` with cases `WORLD SERIES`,
/// `PLAYOFFS` and `DIVISION`, and it is fed `ordered.last`. Measured on
/// `/api/playoffs/{mlb,nfl,nba,nhl}` 2026-09-10 and again 2026-09-18, the last
/// column is `key == "championship"` in every league we serve, and its LABEL is
/// the one thing that differs:
///
/// | league | last label | printed |
/// |---|---|---|
/// | MLB | `World Series` | `WS 24H` — the only case that matched |
/// | NFL | `Super Bowl` | `SUP 24H` |
/// | NBA | `Champion` | `CHA 24H` |
/// | NHL | `Stanley Cup` | `STA 24H` |
///
/// So three of four leagues printed a truncation, and `case "PLAYOFFS"` was dead
/// outright — the served label is `Make Playoffs` and never equalled it.
///
/// THE WORD IS NOT INVENTED HERE. `WIN` is what the repo's only other
/// milestone-abbreviation map already assigns to every championship spelling it
/// knows (`frontend/components/ChampionshipGrid.tsx`: `Super Bowl`, `World Series`,
/// `Stanley Cup`, `Championship` → `WIN`). One word across four leagues also costs
/// the reader nothing, because `rungRow` prints the rung's FULL label directly
/// below the tag either way. If the copy is ever overruled it is this one line.
///
/// Only `championship` and `division` are mapped, deliberately. `championship` is
/// the only column that can reach this tag today; `division` keeps the word it
/// already had. Inventing abbreviations for columns nothing can render would be
/// guessing at copy, so the rest take the truncation — but a SANITIZED one, since
/// MLB's `AL / NL Champ` has `prefix(3) == "AL "` and would have rendered
/// `AL  24H` with a double space the moment a column reorder made it last.
func shortDeltaLabel(key: String?, label: String) -> String {
    let abbrev = deltaTagAbbreviation(key: key, label: label)
    return abbrev.isEmpty ? "24H" : "\(abbrev) 24H"
}

/// The tag's abbreviation alone. Returns `""` when the label offers nothing to
/// abbreviate, which is what makes the trailing/double space unrepresentable
/// rather than merely absent today.
private func deltaTagAbbreviation(key: String?, label: String) -> String {
    switch key {
    case "championship": return "WIN"
    case "division":     return "DIV"
    default:
        return String(label.prefix(3))
            .trimmingCharacters(in: .whitespaces)
            .uppercased()
    }
}

// MARK: - Preview

#Preview("Ladder cards — live, clinched, eliminated") {
    ScrollView {
        VStack(spacing: 12) {
            // Live — design 2b sample (Seattle Mariners)
            LadderCardView(
                title: "Seattle Mariners",
                abbr: "SEA",
                teamColor: Color(hex: "#0C2C56"),
                rank: 5,
                subtitle: "51-40",
                rungs: [
                    LadderRung(id: "po", label: "PLAYOFFS", probability: 0.78),
                    LadderRung(id: "div", label: "DIVISION", probability: 0.61),
                    LadderRung(id: "lcs", label: "LCS", probability: 0.16),
                    LadderRung(id: "ws", label: "WORLD SERIES", probability: 0.069),
                ],
                headlineDeltaLabel: "WIN 24H",
                headlineDelta: -2.2
            )

            // Clinched — design 1f
            LadderCardView(
                title: "Los Angeles Dodgers",
                abbr: "LAD",
                teamColor: Color(hex: "#005A9C"),
                rank: 1,
                subtitle: "58-33",
                rungs: [
                    LadderRung(id: "po", label: "PLAYOFFS", probability: 1.0, state: .clinched),
                    LadderRung(id: "div", label: "DIVISION", probability: 1.0, state: .clinched),
                    LadderRung(id: "lcs", label: "LCS", probability: 0.58),
                    LadderRung(id: "ws", label: "WORLD SERIES", probability: 0.34),
                ],
                clinched: true
            )

            // Eliminated — design 1f (card mutes to 75%)
            LadderCardView(
                title: "Colorado Rockies",
                abbr: "COL",
                teamColor: Color(hex: "#9CA3AF"),
                rank: 28,
                rungs: [
                    LadderRung(id: "po", label: "PLAYOFFS", probability: 0, state: .eliminated),
                    LadderRung(id: "div", label: "DIVISION", probability: 0, state: .eliminated),
                    LadderRung(id: "lcs", label: "LCS", probability: 0, state: .eliminated),
                    LadderRung(id: "ws", label: "WORLD SERIES", probability: 0, state: .eliminated),
                ],
                eliminated: true
            )

            // Prop threshold mode (narrower labels) — design 1g/2e reuse
            LadderCardView(
                title: "Cal Raleigh · Home runs",
                abbr: "SEA",
                teamColor: Color(hex: "#0C2C56"),
                rungs: [
                    LadderRung(id: "40", label: "40+", probability: 0.92),
                    LadderRung(id: "50", label: "50+", probability: 0.61),
                    LadderRung(id: "55", label: "55+", probability: 0.34),
                    LadderRung(id: "60", label: "60+", probability: 0.12),
                ],
                headlineDeltaLabel: "24H",
                headlineDelta: 2.1,
                labelWidth: 34
            )
        }
        .padding(16)
    }
    .background(DS.surface)
}
