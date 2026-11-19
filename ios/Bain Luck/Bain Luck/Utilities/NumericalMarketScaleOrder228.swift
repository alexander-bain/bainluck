import Foundation

/// Direction 228 (#12885): any market whose outcomes are values on a single
/// numerical scale — an "at least N" ladder, disjoint ranges/brackets, a count,
/// a rate, or a margin — lists its rows in ascending numerical order (matching
/// iPhone Margin maps), never by probability. Competitor fields (teams, nominees,
/// candidates, dates) retain their existing probability or chronological order.
nonisolated enum NumericalMarketScaleOrder228 {

    struct ScaleKey: Comparable, Hashable, Sendable {
        let primary: Double
        let relationRank: Int
        let secondary: Double

        static let residual = ScaleKey(primary: .infinity, relationRank: 99, secondary: .infinity)

        var isResidual: Bool { relationRank == 99 }

        static func < (lhs: ScaleKey, rhs: ScaleKey) -> Bool {
            if lhs.primary != rhs.primary { return lhs.primary < rhs.primary }
            if lhs.relationRank != rhs.relationRank { return lhs.relationRank < rhs.relationRank }
            return lhs.secondary < rhs.secondary
        }
    }

    struct OrderedItem<Element> {
        let element: Element
        let originalIndex: Int
        let isLeader: Bool
    }

    // MARK: - Vocabulary & Compiled Patterns

    private static let excludedExactTokens: Set<String> = [
        "yes", "no", "draw", "tie"
    ]

    private static let residualTokens: Set<String> = [
        "other", "others", "any other", "all other", "field", "the field",
        "none", "none of the above"
    ]

    private static let allowedUnitsPattern: String = [
        "%", "percent", "percentage\\s+points?", "pp", "bps", "basis\\s+points?",
        "points?", "pts?", "wins?", "losses?", "games?", "goals?", "runs?",
        "yards?", "yds?", "tds?", "touchdowns?", "rebounds?", "assists?",
        "strikeouts?", "saves?", "sacks?", "blocks?", "steals?", "threes?",
        "aces?", "sets?", "rounds?", "strokes?", "medals?", "seats?", "votes?",
        "cuts?", "hikes?", "raises?", "increases?", "decreases?", "times?",
        "days?", "weeks?", "months?", "hours?", "minutes?",
        "inches", "inch", "in", "cm", "mm", "feet", "ft", "miles?", "mi", "km", "mph",
        "°f", "°c", "°", "degrees?", "deg",
        "k", "m", "b", "t", "bn", "mn", "million", "billion", "trillion", "x"
    ].joined(separator: "|")

    private static let monthOrDateRegex: NSRegularExpression = {
        let months = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
        let pattern = "(?:\\b(?:\(months))\\b|^\\s*(?:before|after|by|prior\\s+to|on\\s+or\\s+before)\\s+\\d{4}\\b|^\\s*q[1-4]\\s+20\\d{2}\\b|\\bmeeting\\b)"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let trailingParenRegex: NSRegularExpression = {
        try! NSRegularExpression(pattern: "\\s*\\([^)]*\\)\\s*$", options: [])
    }()

    private static let policyFallRegex: NSRegularExpression = {
        try! NSRegularExpression(
            pattern: "\\b(?:cut|cuts|lower|lowers|decrease|decreases|decline|declines|ease|eases)\\b",
            options: [.caseInsensitive]
        )
    }()

    private static let policyRiseRegex: NSRegularExpression = {
        try! NSRegularExpression(
            pattern: "\\b(?:hike|hikes|raise|raises|increase|increases|climb|climbs)\\b",
            options: [.caseInsensitive]
        )
    }()

    private static let policyZeroRegex: NSRegularExpression = {
        try! NSRegularExpression(
            pattern: "^(?:no\\s+change|unchanged|no\\s+hike|no\\s+cut|(?:fed\\s+)?maintains?(?:\\s+rate)?|hold|holds)$",
            options: [.caseInsensitive]
        )
    }()

    private static let signedPolicyRungRegex: NSRegularExpression = {
        let verbs = "cut|cuts|lower|lowers|decrease|decreases|decline|declines|ease|eases|hike|hikes|raise|raises|increase|increases|climb|climbs"
        let cmp = "≥|≤|>=|<=|>|<|more\\s+than|less\\s+than|at\\s+least|over|above|under|below"
        let num = "[$€£]?-?\\d[\\d,]*(?:\\.\\d+)?"
        let pattern = "^(?:(?<v1>\(verbs))(?:\\s+by)?\\s*(?<c1>\(cmp))?\\s*(?<n1>\(num))\\s*(?<p1>\\+)?\\s*(?:(?:\(allowedUnitsPattern))\\b)?|(?<c2>\(cmp))?\\s*(?<n2>\(num))\\s*(?<p2>\\+)?\\s*(?:(?:\(allowedUnitsPattern))\\s+)?(?<v2>\(verbs)))$"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let rangeRegex: NSRegularExpression = {
        let num = "[$€£]?(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([kmbt]|bn|mn|%|bps|°[fc]?)?"
        let pattern = "^(?:between\\s+)?\(num)\\s*(?:-|–|—|\\bto\\b|\\band\\b)\\s*\(num)(?:\\s*(?:\(allowedUnitsPattern)))?$"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let prefixComparatorRegex: NSRegularExpression = {
        let cmp = "≥|>=|at\\s+least|no\\s+less\\s+than|>|above|over|more\\s+than|greater\\s+than|higher\\s+than|exceeds?|↑|≤|<=|at\\s+most|no\\s+more\\s+than|up\\s+to|<|below|under|less\\s+than|fewer\\s+than|lower\\s+than|↓|exactly"
        let num = "[$€£]?(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([kmbt]|bn|mn)?"
        let pattern = "^(\(cmp))\\s*\(num)(?:\\s*(?:\(allowedUnitsPattern)))?$"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let suffixComparatorRegex: NSRegularExpression = {
        let num = "[$€£]?(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([kmbt]|bn|mn)?"
        let tail = "\\+|or\\s+(?:more|higher|above|greater)|or\\s+(?:less|fewer|below|lower|under)"
        let pattern = "^\(num)(?:\\s*(?:\(allowedUnitsPattern)))?\\s*(\(tail))(?:\\s*(?:\(allowedUnitsPattern)))?$"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let singleValueRegex: NSRegularExpression = {
        let num = "[$€£]?(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([kmbt]|bn|mn)?"
        let pattern = "^\(num)(?:\\s*(?:\(allowedUnitsPattern)))?$"
        return try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }()

    private static let explicitMarkerRegex: NSRegularExpression = {
        try! NSRegularExpression(
            pattern: "(?:[%$€£°≥≤<>↑↓+]|\\b(?:above|over|under|below|least|most|more|fewer|less|bps|points?|pts?|wins?|inches|cuts?|hikes?|to)\\b|\\d\\s*[-–—]\\s*[$€£]?-?\\d)",
            options: [.caseInsensitive]
        )
    }()

    // MARK: - Scale Detection & Key Extraction

    static func isNumericalScale(
        labels: [String],
        explicitSortKeys: [Double?]? = nil,
        marketType: String? = nil,
        orderHint: String? = nil,
        totalOutcomeCount: Int? = nil
    ) -> Bool {
        scaleKeys(
            for: labels,
            explicitSortKeys: explicitSortKeys,
            marketType: marketType,
            orderHint: orderHint,
            totalOutcomeCount: totalOutcomeCount
        ) != nil
    }

    static func scaleKeys(
        for labels: [String],
        explicitSortKeys: [Double?]? = nil,
        marketType: String? = nil,
        orderHint: String? = nil,
        totalOutcomeCount: Int? = nil
    ) -> [ScaleKey]? {
        let normalizedHint = orderHint?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedHint == "chronological" {
            return nil
        }

        let normalizedType = marketType?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedHint != "numerical", (normalizedType == "claim" || normalizedType == "duel") {
            return nil
        }

        let trimmed = labels.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        guard trimmed.count >= 2 else { return nil }

        let nonEmptyLower = trimmed.map { $0.lowercased() }.filter { !$0.isEmpty }
        guard nonEmptyLower.count == trimmed.count else { return nil }
        if nonEmptyLower.allSatisfy({ excludedExactTokens.contains($0) }) {
            return nil
        }

        // Priority 1: server-supplied per-outcome sort keys (Builder B #12885 contract).
        if let explicitSortKeys, explicitSortKeys.count == labels.count {
            var keys: [ScaleKey] = []
            keys.reserveCapacity(labels.count)
            var numericCount = 0
            var residualCount = 0
            var valid = true
            for (idx, key) in explicitSortKeys.enumerated() {
                if let key, key.isFinite {
                    keys.append(ScaleKey(primary: key, relationRank: 0, secondary: key))
                    numericCount += 1
                } else if residualTokens.contains(nonEmptyLower[idx]) {
                    keys.append(.residual)
                    residualCount += 1
                } else {
                    valid = false
                    break
                }
            }
            if valid, numericCount >= 2, residualCount <= 1 {
                return keys
            }
        }

        // Priority 2: structural single-scale numerical parser.
        let cleaned = trimmed.map(stripExplanatoryParenthetical)
        let signedAxis = usesSignedPolicyAxis(cleaned)

        var keys: [ScaleKey] = []
        keys.reserveCapacity(cleaned.count)
        var numericCount = 0
        var residualCount = 0

        for item in cleaned {
            let lower = item.lowercased()
            if excludedExactTokens.contains(lower) {
                return nil
            }
            if residualTokens.contains(lower) {
                keys.append(.residual)
                residualCount += 1
                continue
            }
            guard let parsed = parseSingleLabel(item, signedAxis: signedAxis) else {
                return nil
            }
            keys.append(parsed)
            numericCount += 1
        }

        guard residualCount <= 1, numericCount >= 2 else { return nil }

        // Require at least 2 distinct scale positions so duplicate/degenerate labels do not trigger.
        let distinctNonResidual = Set(keys.filter { !$0.isResidual })
        guard distinctNonResidual.count >= 2 else { return nil }

        // For 2-item arrays without explicit numerical markers or a larger market outcome count,
        // require >= 3 outcomes when every label is a bare plain number.
        if numericCount == 2,
           normalizedHint != "numerical",
           normalizedType != "quantity",
           (totalOutcomeCount ?? 2) < 3,
           !cleaned.contains(where: { hasExplicitScaleMarker($0) || signedAxis }) {
            return nil
        }

        return keys
    }

    // MARK: - Ordering Helpers

    /// Orders all elements ascending on their numerical scale while marking the modal/answer leader.
    static func orderedAll<Element>(
        _ items: [Element],
        label: (Element) -> String,
        probability: (Element) -> Double?,
        explicitSortKey: ((Element) -> Double?)? = nil,
        marketType: String? = nil,
        orderHint: String? = nil,
        totalOutcomeCount: Int? = nil,
        isCumulative: Bool = false
    ) -> [OrderedItem<Element>]? {
        let labels = items.map(label)
        let explicit = explicitSortKey.map { items.map($0) }
        guard let keys = scaleKeys(
            for: labels,
            explicitSortKeys: explicit,
            marketType: marketType,
            orderHint: orderHint,
            totalOutcomeCount: totalOutcomeCount ?? items.count
        ) else {
            return nil
        }

        let leaderIdx = selectLeaderIndex(probabilities: items.map(probability), isCumulative: isCumulative)
        let sortedIndices = items.indices.sorted { lhs, rhs in
            if keys[lhs] != keys[rhs] {
                return keys[lhs] < keys[rhs]
            }
            return lhs < rhs
        }

        return sortedIndices.map { idx in
            OrderedItem(
                element: items[idx],
                originalIndex: idx,
                isLeader: idx == leaderIdx
            )
        }
    }

    /// Selects up to `limit` items (preserving the #1526 / #10374 invariant that the modal
    /// or crossing outcome never falls off a truncated card) and lists them in ascending
    /// numerical order.
    static func orderedSlice<Element>(
        _ items: [Element],
        limit: Int,
        label: (Element) -> String,
        probability: (Element) -> Double?,
        explicitSortKey: ((Element) -> Double?)? = nil,
        marketType: String? = nil,
        orderHint: String? = nil,
        totalOutcomeCount: Int? = nil,
        isCumulative: Bool = false
    ) -> [OrderedItem<Element>]? {
        guard limit > 0, !items.isEmpty else { return nil }
        let labels = items.map(label)
        let explicit = explicitSortKey.map { items.map($0) }
        guard let keys = scaleKeys(
            for: labels,
            explicitSortKeys: explicit,
            marketType: marketType,
            orderHint: orderHint,
            totalOutcomeCount: totalOutcomeCount ?? items.count
        ) else {
            return nil
        }

        let probs = items.map(probability)
        let chosenIndices: [Int]
        if items.count <= limit {
            chosenIndices = Array(items.indices)
        } else if isCumulative {
            // Cumulative threshold ladders: pick the `limit` rungs nearest 50% (even odds).
            chosenIndices = Array(
                items.indices.sorted { lhs, rhs in
                    let lp = probs[lhs]
                    let rp = probs[rhs]
                    switch (lp, rp) {
                    case let (l?, r?):
                        let ld = abs(l - 0.5)
                        let rd = abs(r - 0.5)
                        if abs(ld - rd) > 1e-9 { return ld < rd }
                        if abs(l - r) > 1e-9 { return l > r }
                        return keys[lhs] < keys[rhs]
                    case (.some, .none): return true
                    case (.none, .some): return false
                    case (.none, .none): return keys[lhs] < keys[rhs]
                    }
                }.prefix(limit)
            )
        } else {
            // Mutually-exclusive numerical scales: keep the `limit` highest-probability
            // buckets (breaking ties by ascending numerical value so `4` beats `5+` on a tie).
            chosenIndices = Array(
                items.indices.sorted { lhs, rhs in
                    let lp = probs[lhs] ?? -1
                    let rp = probs[rhs] ?? -1
                    if abs(lp - rp) > 1e-9 { return lp > rp }
                    if keys[lhs] != keys[rhs] { return keys[lhs] < keys[rhs] }
                    return lhs < rhs
                }.prefix(limit)
            )
        }

        let chosenProbs = chosenIndices.map { probs[$0] }
        let chosenLeaderLocal = selectLeaderIndex(probabilities: chosenProbs, isCumulative: isCumulative)
        let leaderOriginalIndex = chosenLeaderLocal.map { chosenIndices[$0] }

        let ascendingChosen = chosenIndices.sorted { lhs, rhs in
            if keys[lhs] != keys[rhs] {
                return keys[lhs] < keys[rhs]
            }
            return lhs < rhs
        }

        return ascendingChosen.map { idx in
            OrderedItem(
                element: items[idx],
                originalIndex: idx,
                isLeader: idx == leaderOriginalIndex
            )
        }
    }

    // MARK: - Economics FOMC & CPI Helpers

    static func orderedFOMCDistribution(_ dist: [[WeatherAnyCodable]], limit: Int = 5) -> [(rate: String, prob: Double)] {
        let valid: [(rate: String, prob: Double)] = dist.compactMap { pair in
            guard pair.count >= 2,
                  let prob = pair[0].doubleValue,
                  let rate = pair[1].stringValue,
                  prob >= 1 else {
                return nil
            }
            return (rate: rate, prob: prob)
        }
        guard !valid.isEmpty else { return [] }
        if let ordered = orderedSlice(
            valid,
            limit: limit,
            label: \.rate,
            probability: { $0.prob / 100.0 },
            orderHint: "numerical",
            totalOutcomeCount: max(dist.count, valid.count)
        ) {
            return ordered.map(\.element)
        }
        return Array(valid.prefix(limit))
    }

    static func orderedCPIBrackets(
        _ brackets: [[WeatherAnyCodable]],
        fallbackPeakIndex: Int?
    ) -> (brackets: [[WeatherAnyCodable]], peakIndex: Int?) {
        guard brackets.count >= 2 else {
            return (brackets, fallbackPeakIndex)
        }
        let labels = brackets.map { $0.count > 1 ? ($0[1].stringValue ?? "") : "" }
        let probs = brackets.map { $0.first?.doubleValue }
        if let ordered = orderedAll(
            Array(brackets.indices),
            label: { labels[$0] },
            probability: { probs[$0] },
            orderHint: "numerical"
        ) {
            let reordered = ordered.map { brackets[$0.originalIndex] }
            let newPeak = ordered.firstIndex(where: \.isLeader) ?? fallbackPeakIndex
            return (reordered, newPeak)
        }
        return (brackets, fallbackPeakIndex)
    }

    // MARK: - Internal Label Parsing

    static func parseLabelKey(_ raw: String, signedAxis: Bool = false) -> ScaleKey? {
        let cleaned = stripExplanatoryParenthetical(raw.trimmingCharacters(in: .whitespacesAndNewlines))
        let lower = cleaned.lowercased()
        if excludedExactTokens.contains(lower) { return nil }
        if residualTokens.contains(lower) { return .residual }
        return parseSingleLabel(cleaned, signedAxis: signedAxis)
    }

    private static func selectLeaderIndex(probabilities: [Double?], isCumulative: Bool) -> Int? {
        guard !probabilities.isEmpty else { return nil }
        if isCumulative {
            var bestIdx: Int? = nil
            for (idx, prob) in probabilities.enumerated() {
                guard let prob, prob.isFinite else { continue }
                guard let current = bestIdx, let currentProb = probabilities[current] else {
                    bestIdx = idx
                    continue
                }
                let dist = abs(prob - 0.5)
                let bestDist = abs(currentProb - 0.5)
                if dist + 1e-9 < bestDist || (abs(dist - bestDist) <= 1e-9 && prob > currentProb + 1e-9) {
                    bestIdx = idx
                }
            }
            return bestIdx ?? 0
        } else {
            var bestIdx = 0
            var bestProb = probabilities[0] ?? -Double.infinity
            for (idx, prob) in probabilities.enumerated() {
                let candidate = prob ?? -Double.infinity
                if candidate > bestProb + 1e-9 {
                    bestProb = candidate
                    bestIdx = idx
                }
            }
            return bestIdx
        }
    }

    private static func stripExplanatoryParenthetical(_ text: String) -> String {
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = trailingParenRegex.firstMatch(in: text, options: [], range: range),
              let matchRange = Range(match.range, in: text) else {
            return text
        }
        let prefix = String(text[..<matchRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prefix.isEmpty else { return text }
        let hasDigit = prefix.unicodeScalars.contains(where: { CharacterSet.decimalDigits.contains($0) })
        let prefixNSRange = NSRange(prefix.startIndex..<prefix.endIndex, in: prefix)
        let isZeroPolicy = policyZeroRegex.firstMatch(in: prefix, options: [], range: prefixNSRange) != nil
        return (hasDigit || isZeroPolicy) ? prefix : text
    }

    private static func usesSignedPolicyAxis(_ labels: [String]) -> Bool {
        var hasFall = false
        var hasRise = false
        var hasZero = false
        for item in labels {
            let r = NSRange(item.startIndex..<item.endIndex, in: item)
            if policyZeroRegex.firstMatch(in: item, options: [], range: r) != nil {
                hasZero = true
                continue
            }
            let hasDigit = item.unicodeScalars.contains(where: { CharacterSet.decimalDigits.contains($0) })
            guard hasDigit else { continue }
            if policyFallRegex.firstMatch(in: item, options: [], range: r) != nil {
                hasFall = true
            }
            if policyRiseRegex.firstMatch(in: item, options: [], range: r) != nil {
                hasRise = true
            }
        }
        return (hasFall && hasRise) || (hasFall && hasZero) || (hasRise && hasZero)
    }

    private static func hasExplicitScaleMarker(_ text: String) -> Bool {
        let r = NSRange(text.startIndex..<text.endIndex, in: text)
        return explicitMarkerRegex.firstMatch(in: text, options: [], range: r) != nil
    }

    private static func parseSingleLabel(_ text: String, signedAxis: Bool) -> ScaleKey? {
        guard !text.isEmpty else { return nil }
        let fullRange = NSRange(text.startIndex..<text.endIndex, in: text)

        // Never treat calendar dates or meeting months as numerical scales.
        if monthOrDateRegex.firstMatch(in: text, options: [], range: fullRange) != nil {
            return nil
        }

        if signedAxis {
            if policyZeroRegex.firstMatch(in: text, options: [], range: fullRange) != nil {
                return ScaleKey(primary: 0, relationRank: 0, secondary: 0)
            }
            if let signed = parseSignedPolicyRung(text, range: fullRange) {
                return signed
            }
        }

        // 1. Explicit range (`3.75%–4.00%`, `$100M - $150M`, `-5.5 to -2.5`, `Between 2% and 3%`).
        if let match = rangeRegex.firstMatch(in: text, options: [], range: fullRange),
           let lowRaw = substring(text, match.range(at: 1)),
           let highRaw = substring(text, match.range(at: 3)),
           let lowBase = parseNumber(lowRaw),
           let highBase = parseNumber(highRaw) {
            let lowMult = magnitudeMultiplier(substring(text, match.range(at: 2)))
            let highMult = magnitudeMultiplier(substring(text, match.range(at: 4)))
            let effectiveLowMult = (lowMult == 1.0 && highMult > 1.0 && abs(lowBase) < 10_000) ? highMult : lowMult
            let effectiveHighMult = (highMult == 1.0 && lowMult > 1.0 && abs(highBase) < 10_000) ? lowMult : highMult
            let a = lowBase * effectiveLowMult
            let b = highBase * effectiveHighMult
            return ScaleKey(primary: min(a, b), relationRank: 1, secondary: max(a, b))
        }

        // 2. Prefix comparator (`≥ 4.5%`, `≤1.0%`, `Above 6 inches`, `Under 2.5`, `↑ 4.25%`).
        if let match = prefixComparatorRegex.firstMatch(in: text, options: [], range: fullRange),
           let cmpRaw = substring(text, match.range(at: 1)),
           let numRaw = substring(text, match.range(at: 2)),
           let base = parseNumber(numRaw) {
            let mult = magnitudeMultiplier(substring(text, match.range(at: 3)))
            let val = base * mult
            let rel = relationRankForPrefix(cmpRaw)
            return ScaleKey(primary: val, relationRank: rel, secondary: val)
        }

        // 3. Suffix comparator (`4+`, `6.5+ wins`, `84°F or higher`, `59°F or below`).
        if let match = suffixComparatorRegex.firstMatch(in: text, options: [], range: fullRange),
           let numRaw = substring(text, match.range(at: 1)),
           let tailRaw = substring(text, match.range(at: 3)),
           let base = parseNumber(numRaw) {
            let mult = magnitudeMultiplier(substring(text, match.range(at: 2)))
            let val = base * mult
            let lowerTail = tailRaw.lowercased()
            let isLower = lowerTail.contains("less") || lowerTail.contains("fewer")
                || lowerTail.contains("below") || lowerTail.contains("lower") || lowerTail.contains("under")
            return ScaleKey(primary: val, relationRank: isLower ? -1 : 2, secondary: val)
        }

        // 4. Bare number or number + unit (`1`, `2`, `3.75%`, `$100`, `25bps`, `72°F`).
        if let match = singleValueRegex.firstMatch(in: text, options: [], range: fullRange),
           let numRaw = substring(text, match.range(at: 1)),
           let base = parseNumber(numRaw) {
            let mult = magnitudeMultiplier(substring(text, match.range(at: 2)))
            let val = base * mult
            return ScaleKey(primary: val, relationRank: 0, secondary: val)
        }

        return nil
    }

    private static func parseSignedPolicyRung(_ text: String, range: NSRange) -> ScaleKey? {
        guard let match = signedPolicyRungRegex.firstMatch(in: text, options: [], range: range) else {
            return nil
        }
        let verb = substring(text, match.range(withName: "v1")) ?? substring(text, match.range(withName: "v2")) ?? ""
        let cmp = substring(text, match.range(withName: "c1")) ?? substring(text, match.range(withName: "c2"))
        let numStr = substring(text, match.range(withName: "n1")) ?? substring(text, match.range(withName: "n2"))
        let plus = substring(text, match.range(withName: "p1")) ?? substring(text, match.range(withName: "p2"))
        guard let numStr, let rawMag = parseNumber(numStr) else { return nil }

        let mag = abs(rawMag)
        let verbRange = NSRange(verb.startIndex..<verb.endIndex, in: verb)
        let isFall = policyFallRegex.firstMatch(in: verb, options: [], range: verbRange) != nil

        var baseRel = 0
        if let cmp {
            baseRel = relationRankForPrefix(cmp)
        } else if plus != nil {
            baseRel = 2
        }

        if isFall {
            // "Cut >25bps" (-25, rel -3) < "Cut 25bps" (-25, rel 0) < "No change" (0, 0).
            let mirroredRel = -baseRel
            return ScaleKey(primary: -mag, relationRank: mirroredRel, secondary: -mag)
        } else {
            return ScaleKey(primary: mag, relationRank: baseRel, secondary: mag)
        }
    }

    private static func relationRankForPrefix(_ raw: String) -> Int {
        let lower = raw
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        switch lower {
        case "<", "below", "under", "less than", "fewer than", "lower than":
            return -2
        case "≤", "<=", "at most", "no more than", "up to", "↓":
            return -1
        case "≥", ">=", "at least", "no less than", "↑":
            return 2
        case ">", "above", "over", "more than", "greater than", "higher than", "exceed", "exceeds":
            return 3
        default:
            return 0
        }
    }

    private static func parseNumber(_ raw: String) -> Double? {
        let clean = raw
            .replacingOccurrences(of: ",", with: "")
            .replacingOccurrences(of: "$", with: "")
            .replacingOccurrences(of: "€", with: "")
            .replacingOccurrences(of: "£", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard let val = Double(clean), val.isFinite else { return nil }
        return val
    }

    private static func magnitudeMultiplier(_ suffix: String?) -> Double {
        guard let s = suffix?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), !s.isEmpty else {
            return 1.0
        }
        switch s {
        case "k": return 1_000
        case "m", "mn", "million": return 1_000_000
        case "b", "bn", "billion": return 1_000_000_000
        case "t", "trillion": return 1_000_000_000_000
        default: return 1.0
        }
    }

    private static func substring(_ text: String, _ nsRange: NSRange) -> String? {
        guard nsRange.location != NSNotFound, let range = Range(nsRange, in: text) else {
            return nil
        }
        return String(text[range])
    }
}
