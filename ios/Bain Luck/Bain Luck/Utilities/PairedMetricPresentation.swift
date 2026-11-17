import Foundation

// MARK: - Pure Presentation & Safety Rules for Paired-Metric Grouped Cards (#12642 / #12577)

nonisolated enum PairedStageDisplayKind: String, Equatable, Sendable {
    case percent
    case tick
    case cross
    case missing
}

nonisolated struct FormattedPairedStageDisplay: Equatable, Sendable {
    let kind: PairedStageDisplayKind
    let percent: Int?
    let symbol: String?
    let label: String
    let sublabel: String?

    init(
        kind: PairedStageDisplayKind,
        percent: Int?,
        symbol: String? = nil,
        label: String,
        sublabel: String? = nil
    ) {
        self.kind = kind
        self.percent = percent
        self.symbol = symbol
        self.label = label
        self.sublabel = sublabel
    }
}

nonisolated struct PairedPodiumSpot: Equatable, Sendable {
    let rank: Int
    let badge: String
    let entry: PairedSubjectEntry
    let elevated: Bool
}

nonisolated struct PairedPodiumPartition: Equatable, Sendable {
    /// Visual column order: `[#2 CHASER (left), #1 LEADER (center, elevated), #3 CONTENDER (right)]`.
    let podiumSpots: [PairedPodiumSpot]
    /// Remaining entries (`sorted.dropFirst(3)`) at `>= 70%` Stage 1 probability.
    let lockTier: [PairedSubjectEntry]
    /// Remaining entries (`sorted.dropFirst(3)`) at `< 70%` Stage 1 probability.
    let bubbleTier: [PairedSubjectEntry]
}

nonisolated enum PairedMetricPresentation {
    static let tmdbAttributionLine = "This product uses the TMDB API but is not endorsed or certified by TMDB."
    static let tmdbAttributionURL = URL(string: "https://www.themoviedb.org/")!
    static let tmdbHorrorGenreId = 27
    static let allowedVisualArtHosts: Set<String> = [
        "image.tmdb.org",
        "a.espncdn.com",
        "images.pexels.com"
    ]

    // Mirrors `frontend/lib/play/kidSafe.ts` (#7461).
    private static let exactBlockedTerms: [String] = [
        "war", "wars", "gun", "guns", "die", "died", "dies", "dead", "coup", "coups", "stab"
    ]

    private static let prefixBlockedTerms: [String] = [
        "death", "invade", "invaded", "invasion", "invad", "invas", "pandemic", "virus", "viru",
        "pregnan", "regime", "election", "crypto", "divorce", "affair", "mistress", "adulter",
        "breakup", "dating", "romance", "hookup", "cheat", "engag", "kill", "murder", "terror",
        "bomb", "missile", "nuclear", "hostage", "warfare", "warhead", "genocide", "massacre",
        "execut", "kidnap", "slaughter", "behead", "torture", "corpse", "homicide", "manslaughter",
        "fatal", "weapon", "casualt", "wound", "assault", "riot", "shooting", "shooter", "gunman",
        "gunfire", "gunshot", "gunned", "stabbed", "stabbing", "airstrike", "insurgen", "jihad",
        "isis", "hamas", "hezbollah", "covid", "overdos", "suicide", "drug", "cartel", "bitcoin",
        "ethereum", "abortion", "rape", "raped", "sexual", "incest", "pedophile", "traffick",
        "molest", "naked", "nude", "nudity", "porn"
    ]

    private static let exactRegex: NSRegularExpression = {
        let pattern = "\\b(?:" + exactBlockedTerms.joined(separator: "|") + ")\\b"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let prefixRegex: NSRegularExpression = {
        let pattern = "\\b(?:" + prefixBlockedTerms.joined(separator: "|") + ")"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    /// True when the text passes the `#7461` term blocklist (`frontend/lib/play/kidSafe.ts`).
    static func isKidSafeText(_ text: String?) -> Bool {
        guard let text, !text.isEmpty else { return true }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        if exactRegex.firstMatch(in: text, options: [], range: range) != nil {
            return false
        }
        if prefixRegex.firstMatch(in: text, options: [], range: range) != nil {
            return false
        }
        return true
    }

    /// `#7461` Kid-Safe & host validation gate for per-outcome posters, headshots, and team logos.
    static func resolveKidSafeVisualArt(_ entry: PairedSubjectEntry) -> URL? {
        guard let art = entry.art, !art.url.isEmpty else { return nil }
        guard !art.adult, art.kidSafeVetted else { return nil }
        if let genres = art.genreIds, genres.contains(tmdbHorrorGenreId) {
            return nil
        }
        guard isKidSafeText(entry.subject), isKidSafeText(entry.detail) else {
            return nil
        }
        guard let parsed = URL(string: art.url),
              let scheme = parsed.scheme?.lowercased(), scheme == "https",
              let host = parsed.host?.lowercased(),
              allowedVisualArtHosts.contains(host) else {
            return nil
        }
        return parsed
    }

    /// Deterministic 2-letter uppercase initials tile text for missing/blocked art.
    static func initials(for subject: String) -> String {
        let words = subject
            .split(whereSeparator: { $0.isWhitespace })
            .prefix(2)
        let letters = words.compactMap { word -> String? in
            guard let ch = word.first(where: { $0.isLetter || $0.isNumber }) ?? word.first else {
                return nil
            }
            return String(ch).uppercased()
        }.joined()
        return letters.isEmpty ? "—" : letters
    }

    /// Deterministic tie-breaking rule (`visualForms.ts` `sortPairedEntries`):
    /// 1. Listed Stage 2 contenders before unlisted (`stage2Probability != nil` & finite),
    /// 2. Higher `stage2Probability` (within `1e-6` tolerance),
    /// 3. Higher `stage1Probability` (within `1e-6` tolerance),
    /// 4. Alphabetical by `subject`.
    static func sortPairedEntries(_ entries: [PairedSubjectEntry]) -> [PairedSubjectEntry] {
        entries.sorted { a, b in
            let aHasS2 = a.stage2Probability?.isFinite == true
            let bHasS2 = b.stage2Probability?.isFinite == true
            if aHasS2 != bHasS2 {
                return aHasS2
            }
            let aS2 = a.stage2Probability ?? -1
            let bS2 = b.stage2Probability ?? -1
            if abs(bS2 - aS2) > 1e-6 {
                return aS2 > bS2
            }
            let aS1 = a.stage1Probability ?? -1
            let bS1 = b.stage1Probability ?? -1
            if abs(bS1 - aS1) > 1e-6 {
                return aS1 > bS1
            }
            return a.subject.localizedStandardCompare(b.subject) == .orderedAscending
        }
    }

    /// Strips internal venue notes and `#market_id` annotations from card-face subtitles (`139-A` / `141`).
    static func formatCardFaceSubtitle(_ subtitle: String) -> String {
        var result = subtitle
        let patterns = [
            "\\s*·\\s*Nominee\\s*%.*$",
            "\\s*·\\s*Paired by club.*$",
            "\\s*\\([^)]*#\\d+[^)]*\\)"
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                let range = NSRange(result.startIndex..<result.endIndex, in: result)
                result = regex.stringByReplacingMatches(in: result, options: [], range: range, withTemplate: "")
            }
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Formats Stage 1 (`Nominated %` / `Make Playoffs %`) via `renderedPercent`, clamped to `1..99%` while open.
    static func formatStage1Display(
        entry: PairedSubjectEntry,
        set: PairedMetricSet
    ) -> FormattedPairedStageDisplay {
        let settled = entry.stage1SettledState?.lowercased()
        if settled == "yes" {
            return FormattedPairedStageDisplay(
                kind: .tick,
                percent: 100,
                symbol: "✓",
                label: "✓ \(set.stage1SettledYesLabel)"
            )
        }
        if settled == "no" {
            let priorPct = renderedPercent(entry.stage1Probability).map { max(1, min(99, $0)) }
            return FormattedPairedStageDisplay(
                kind: .cross,
                percent: 0,
                symbol: "✗",
                label: "✗ \(set.stage1SettledNoLabel)",
                sublabel: priorPct.map { "was \($0)%" }
            )
        }
        guard let rawPct = renderedPercent(entry.stage1Probability) else {
            let fallback = (entry.missingStage1Reason?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
                ?? "No recent \(set.stage1Label.lowercased()) %"
            return FormattedPairedStageDisplay(kind: .missing, percent: nil, label: fallback)
        }
        let pct = max(1, min(99, rawPct))
        return FormattedPairedStageDisplay(kind: .percent, percent: pct, label: "\(pct)%")
    }

    /// Formats Stage 2 (`Wins %` / `Win Cup %`) via `renderedPercent`, clamped to `1..99%` while open,
    /// never blending with Stage 1, and explicitly reporting unlisted / missing rows.
    static func formatStage2Display(
        entry: PairedSubjectEntry,
        set: PairedMetricSet
    ) -> FormattedPairedStageDisplay {
        if entry.stage1SettledState?.lowercased() == "no" {
            return FormattedPairedStageDisplay(
                kind: .cross,
                percent: 0,
                symbol: "✗",
                label: "Eliminated"
            )
        }
        guard let rawPct = renderedPercent(entry.stage2Probability) else {
            let fallback = (entry.missingStage2Reason?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
                ?? "Not listed to win"
            return FormattedPairedStageDisplay(kind: .missing, percent: nil, label: fallback)
        }
        let pct = max(1, min(99, rawPct))
        return FormattedPairedStageDisplay(kind: .percent, percent: pct, label: "\(pct)%")
    }

    /// Proportional `0.0...1.0` fill width behind a percentage readout box (`94%` -> `0.94`,
    /// `36%` -> `0.36`), or `nil` when the stage is settled (`✓`/`✗`) or unpriced.
    static func quietFillFraction(for display: FormattedPairedStageDisplay) -> Double? {
        guard display.kind == .percent, let pct = display.percent else { return nil }
        return min(1.0, max(0.0, Double(pct) / 100.0))
    }

    /// True when the sanitized card-face subtitle already explains the sort/tie-break rule,
    /// avoiding repeating the same ordering sentence in the card footer.
    static func subtitleStatesOrdering(_ cleanSubtitle: String) -> Bool {
        let lower = cleanSubtitle.lowercased()
        return lower.contains("ordered by")
            || lower.contains("sorted by")
            || lower.contains("ties broken by")
    }

    /// Short Stage-1 qualifier tag (`"nom"`, `"playoff"`, or lowercased `stage1Label`).
    static func shortStage1Tag(for set: PairedMetricSet) -> String {
        let lower = set.stage1Label.lowercased()
        if lower.contains("nominat") { return "nom" }
        if lower.contains("playoff") { return "playoff" }
        return lower
    }

    /// Short Stage-2 qualifier tag (`"win"`).
    static func shortStage2Tag(for set: PairedMetricSet) -> String {
        let lower = set.stage2Label.lowercased()
        if lower.contains("win") { return "win" }
        return lower
    }

    /// Look 1 collapsed expander headline + optional unpriced-contender callout line.
    static func expanderCopy(
        sortedEntries: [PairedSubjectEntry],
        set: PairedMetricSet,
        expanded: Bool
    ) -> (primary: String, unpricedNotice: String?)? {
        let hiddenCount = sortedEntries.count - 5
        guard hiddenCount > 0 else { return nil }
        if expanded {
            return (primary: "Show top 5 by \(set.stage2Label) % only", unpricedNotice: nil)
        }
        let primary: String
        if set.stage1Label.lowercased().contains("nominat") {
            primary = "Show all \(sortedEntries.count) most likely nominees (+\(hiddenCount) more)"
        } else {
            primary = "Show all \(sortedEntries.count) contenders (+\(hiddenCount) more)"
        }
        let hiddenSlice = sortedEntries.dropFirst(5)
        guard let unpriced = hiddenSlice.first(where: { $0.stage2Probability == nil }) else {
            return (primary: primary, unpricedNotice: nil)
        }
        let s1 = formatStage1Display(entry: unpriced, set: set)
        let s2 = formatStage2Display(entry: unpriced, set: set)
        let s1Part = s1.kind == .percent ? "\(s1.label) \(shortStage1Tag(for: set))" : s1.label
        let notice = "incl. \(unpriced.subject) (\(s1Part) · \(s2.label))"
        return (primary: primary, unpricedNotice: notice)
    }

    /// Look 2 podium (`[#2, #1, #3]`) + `70%+` / `<70%` tier partition. Returns `nil` if fewer than 3 entries.
    static func podiumPartition(for set: PairedMetricSet) -> PairedPodiumPartition? {
        let sorted = sortPairedEntries(set.entries)
        guard sorted.count >= 3 else { return nil }
        let spots = [
            PairedPodiumSpot(rank: 2, badge: "#2 CHASER", entry: sorted[1], elevated: false),
            PairedPodiumSpot(rank: 1, badge: "#1 LEADER", entry: sorted[0], elevated: true),
            PairedPodiumSpot(rank: 3, badge: "#3 CONTENDER", entry: sorted[2], elevated: false)
        ]
        let remaining = Array(sorted.dropFirst(3))
        let lockTier = remaining.filter { (renderedPercent($0.stage1Probability) ?? 0) >= 70 }
        let bubbleTier = remaining.filter { (renderedPercent($0.stage1Probability) ?? 0) < 70 }
        return PairedPodiumPartition(podiumSpots: spots, lockTier: lockTier, bubbleTier: bubbleTier)
    }

    /// Domain-aware tier box headings for Look 2 (`podium_and_tiers`).
    static func tierHeaderCopy(for set: PairedMetricSet, isLockTier: Bool) -> (left: String, right: String) {
        let lowerS1 = set.stage1Label.lowercased()
        if lowerS1.contains("nominat") {
            let left = isLockTier
                ? "LIKELY NOMINEES (70%+ TO BE NOMINATED · LONGSHOT TO WIN)"
                : "ON THE NOMINATION BUBBLE (<70% TO BE NOMINATED)"
            return (left, "NOM · WIN")
        }
        if lowerS1.contains("playoff") {
            let left = isLockTier
                ? "LIKELY PLAYOFF CLUBS (70%+ PLAYOFFS · LONGSHOT TO WIN)"
                : "ON THE PLAYOFF BUBBLE (<70% PLAYOFFS)"
            return (left, "PLAYOFF · WIN")
        }
        let s1Upper = set.stage1Label.uppercased()
        let s2Upper = set.stage2Label.uppercased()
        let left = isLockTier
            ? "LIKELY \(s1Upper) (70%+)"
            : "ON THE BUBBLE (<70% \(s1Upper))"
        return (left, "\(s1Upper) · \(s2Upper)")
    }

    /// Resolves which of the two winning grouped looks to draw, honoring explicit server preference
    /// when valid, falling back to `.pairedBarsTop5Expandable` if `< 3` entries, and alternating
    /// deterministically across cards when unspecified so adjacent grouped cards differ (`168-A`).
    static func resolvedForm(
        for set: PairedMetricSet,
        preferred: String? = nil,
        cardIndex: Int? = nil
    ) -> PairedVisualFormId {
        let candidate = preferred ?? set.preferredVisualForm
        if let candidate, let explicit = PairedVisualFormId(rawValue: candidate) {
            if explicit == .podiumAndTiers && set.entries.count < 3 {
                return .pairedBarsTop5Expandable
            }
            return explicit
        }
        guard set.entries.count >= 3 else {
            return .pairedBarsTop5Expandable
        }
        if let cardIndex {
            return cardIndex.isMultiple(of: 2) ? .pairedBarsTop5Expandable : .podiumAndTiers
        }
        let hash = set.setId.utf8.reduce(0) { ($0 &* 31) &+ Int($1) }
        return (abs(hash) % 2 == 0) ? .pairedBarsTop5Expandable : .podiumAndTiers
    }
}
