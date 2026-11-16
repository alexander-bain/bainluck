import SwiftUI

/// Direction 199 & Ruling 200-B — Single canonical typography and colour table
/// for game headlines across the event page, feed/Discover cards, Home Screen
/// widget, and Apple Watch wrist tile.
///
/// Five typography styles (`now`, `secondNumbers`, `quietText`, `names`,
/// `headers`) and shared semantic ink tokens live here in one file. Percent
/// formatting intentionally remains on the app's existing `formatProbability`,
/// `RenderedPercent`, and `EventHeadlineTenths10090` helpers — no formatter is
/// defined here.
nonisolated enum HeadlineStyleTable199 {
    enum Surface: String, CaseIterable, Equatable, Sendable {
        case page
        case card
        case widget
        case wristTile
    }

    // MARK: - Base Point Metrics (for @ScaledMetric or direct layout measurement)

    static func nowBaseSize(_ surface: Surface) -> CGFloat {
        switch surface {
        case .page: return 26
        case .card: return 16
        case .widget: return 27
        case .wristTile: return 17
        }
    }

    static func secondNumberBaseSize(_ surface: Surface, prominent: Bool = false) -> CGFloat {
        switch surface {
        case .page: return prominent ? 22 : 17
        case .card: return prominent ? 15 : 13
        case .widget: return prominent ? 20 : 13
        case .wristTile: return prominent ? 15 : 12
        }
    }

    static func quietTextBaseSize(_ surface: Surface) -> CGFloat {
        switch surface {
        case .page: return 12
        case .card: return 11.5
        case .widget: return 11
        case .wristTile: return 11
        }
    }

    static func nameBaseSize(_ surface: Surface) -> CGFloat {
        switch surface {
        case .page: return 15.5
        case .card: return 15
        case .widget: return 13
        case .wristTile: return 13
        }
    }

    static func headerBaseSize(_ surface: Surface) -> CGFloat {
        switch surface {
        case .page: return 11
        case .card: return 11
        case .widget: return 10
        case .wristTile: return 10
        }
    }

    // MARK: - 1. `now`: Primary Win Chance (largest number on the surface, in team colour)

    static func now(_ surface: Surface = .page, scaledSize: CGFloat? = nil) -> Font {
        let size = scaledSize ?? nowBaseSize(surface)
        switch surface {
        case .page:
            return .system(size: min(size, 32), weight: .black, design: .rounded).monospacedDigit()
        case .card:
            return .system(size: min(size, 22), weight: .heavy, design: .rounded).monospacedDigit()
        case .widget:
            return .system(size: size, weight: .bold, design: .rounded).monospacedDigit()
        case .wristTile:
            return .title3.bold().monospacedDigit()
        }
    }

    // MARK: - 2. `secondNumbers`: Score, Proj., Final, Set Games, and Final Pregame Column

    static func secondNumbers(
        _ surface: Surface = .page,
        prominent: Bool = false,
        scaledSize: CGFloat? = nil
    ) -> Font {
        let size = scaledSize ?? secondNumberBaseSize(surface, prominent: prominent)
        switch surface {
        case .page:
            let weight: Font.Weight = prominent ? .heavy : .semibold
            let cap: CGFloat = prominent ? 28 : 22
            return .system(size: min(size, cap), weight: weight, design: .rounded).monospacedDigit()
        case .card:
            let weight: Font.Weight = prominent ? .bold : .semibold
            return .system(size: min(size, 20), weight: weight, design: .rounded).monospacedDigit()
        case .widget:
            let weight: Font.Weight = prominent ? .bold : .semibold
            return .system(size: size, weight: weight, design: .rounded).monospacedDigit()
        case .wristTile:
            return (prominent ? Font.body.bold() : Font.footnote.weight(.semibold)).monospacedDigit()
        }
    }

    // MARK: - 3. `quietText`: Single Grey Pregame Line, Team Record, and Plain Meta

    static func quietText(
        _ surface: Surface = .page,
        monospacedDigits: Bool = true,
        scaledSize: CGFloat? = nil
    ) -> Font {
        let base: Font
        if let scaledSize {
            let weight: Font.Weight = surface == .card ? .regular : .medium
            base = .system(size: scaledSize, weight: weight)
        } else {
            switch surface {
            case .page:
                base = .caption.weight(.medium)
            case .card:
                base = .caption.weight(.regular)
            case .widget:
                base = .caption2.weight(.medium)
            case .wristTile:
                base = .caption2.weight(.medium)
            }
        }
        return monospacedDigits ? base.monospacedDigit() : base
    }

    // MARK: - 4. `names`: Competitor / School / Club / Player Name

    static func names(
        _ surface: Surface = .page,
        isLoser: Bool = false,
        scaledSize: CGFloat? = nil
    ) -> Font {
        let weight: Font.Weight = isLoser ? .semibold : .bold
        if let scaledSize {
            return .system(size: scaledSize, weight: weight)
        }
        switch surface {
        case .page, .card:
            return .subheadline.weight(weight)
        case .widget:
            return .footnote.weight(.semibold)
        case .wristTile:
            return .footnote.weight(.semibold)
        }
    }

    // MARK: - 5. `headers`: Column Headers (`Score`, `Proj.`, `Now`, `Chance`, `Pregame`, `Final`)

    static func headers(_ surface: Surface = .page, scaledSize: CGFloat? = nil) -> Font {
        if let scaledSize {
            return .system(size: min(scaledSize, 15), weight: .semibold)
        }
        switch surface {
        case .page, .card:
            return .caption2.weight(.semibold)
        case .widget, .wristTile:
            return .caption2.weight(.semibold)
        }
    }

    // MARK: - Canonical Semantic Colours

    /// AA-readable quiet slate (`#526071` on light, `#94A3B8` via `.secondary` blend)
    /// used for column headers, the single grey pregame line under the bar, and records.
    static let quietInk = Color(red: 82.0 / 255.0, green: 96.0 / 255.0, blue: 113.0 / 255.0)

    /// Primary ink for active scores, finals, and live projected totals.
    static let primaryNumberInk = Color.primary

    /// Quieter ink for settled losers so winners lead without erasing the opponent.
    static let loserInk = Color.primary.opacity(0.65)

    /// Emerald tick (`✓`) next to the decided winner on finished games.
    static let winnerTickInk = Color(red: 0.09, green: 0.56, blue: 0.30)

    /// Quiet light cool grey (`#94A3B8`, `slate-400`) for three-way soccer's `Draw`
    /// row, kept visibly lighter than a team's `#64748B` (`slate-500`) fallback so
    /// `Draw` never looks like a team on the slate fallback.
    static let drawInk = Color(red: 148.0 / 255.0, green: 163.0 / 255.0, blue: 184.0 / 255.0)

    /// Lighter silver-grey (`#CBD5E1`, `slate-300`) for the middle `Draw` segment
    /// in three-way soccer's probability bar so a `#64748B` slate team segment
    /// reads unmistakably darker beside it.
    static let drawBarInk = Color(red: 203.0 / 255.0, green: 213.0 / 255.0, blue: 225.0 / 255.0)

    /// Live pill background red and foreground white.
    static let livePillInk = Color(red: 220.0 / 255.0, green: 38.0 / 255.0, blue: 38.0 / 255.0)
    static let livePillForegroundInk = Color.white

    /// Subtle hairline divider and card border inks.
    static let rowDividerInk = Color.primary.opacity(0.06)
    static let headerRuleInk = Color.primary.opacity(0.08)
    static let cardBorderInk = Color.primary.opacity(0.08)
}
