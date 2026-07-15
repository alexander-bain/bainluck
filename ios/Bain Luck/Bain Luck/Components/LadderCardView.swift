import SwiftUI

// MARK: - Ladder primitive (QuantityGroup analogue)
//
// One question, many milestones/thresholds, one card. This is the native port of
// the web `QuantityGroup` "ladder-strip" kernel and the adopted "2b" design from the
// Native Championship Grids handoff (docs/archive/designs/.../Native Championship Grids.dc.html,
// Turn 3: "2b adopted as the ladder component").
//
// It supersedes the compact `ProgressionLadderView` (feed variant) for the full
// per-team / per-prop context. Championship milestones and prop thresholds are the
// same shape — "one component, two label modes" (design note 1g). League-screen
// assembly (design 2c) is the follow-up (L2-123).

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
    var headlineDeltaLabel: String? = nil   // e.g. "WS 24H"
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

extension LadderCardView {
    /// Build a per-team ladder card from the championship-grid models
    /// (`GridTeam` + ordered `[GridColumn]`). The last column's 24h trend becomes the
    /// headline delta ("WS 24H"), matching the design's per-card delta.
    init(gridTeam team: GridTeam, columns: [GridColumn], rank: Int? = nil) {
        let ordered = columns.sorted { $0.order < $1.order }
        let rungs = ordered.map { col -> LadderRung in
            let cell = team.cells[col.key]
            return LadderRung(id: col.key, label: col.label, probability: cell?.mergedProbability)
        }
        let lastKey = ordered.last?.key
        let lastLabel = ordered.last?.label
        let trend = lastKey.flatMap { team.cells[$0]?.trend24H }

        self.init(
            title: team.name,
            abbr: team.shortName,
            logoUrl: team.logoUrl,
            teamColor: team.primaryColor.map { Color(hex: $0) } ?? DS.emeraldDark,
            rank: rank ?? team.seed,
            subtitle: team.record,
            rungs: rungs,
            headlineDeltaLabel: lastLabel.map { shortDeltaLabel($0) },
            headlineDelta: trend.map { $0 * 100 }
        )
    }
}

/// Abbreviates a milestone label for the compact "… 24H" header tag ("WORLD SERIES" → "WS 24H").
private func shortDeltaLabel(_ label: String) -> String {
    let abbrev: String
    switch label.uppercased() {
    case "WORLD SERIES": abbrev = "WS"
    case "PLAYOFFS":     abbrev = "PO"
    case "DIVISION":     abbrev = "DIV"
    default:             abbrev = String(label.prefix(3)).uppercased()
    }
    return "\(abbrev) 24H"
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
                headlineDeltaLabel: "WS 24H",
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
