import SwiftUI

struct PlayerPropsCardView: View {
    let playerProps: [GameMarketPlayerProp]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    let eventStatus: String?
    /// #4018 — needed for the caption alone. `eventStatus` cannot answer "did
    /// this game stop?" by itself: `suspended` is a status, not a phase, and
    /// #4021's future-dated row proves the two disagree. `EventState` asks the
    /// clock, so the clock has to travel.
    var commenceTime: Date?
    var boxScore: [String: [String: Double]]?

    @State private var teamFilter: String = "all"
    @State private var expandedCards: Set<String> = []

    /// #3430 — both competitors of one matchup, so the pair rule decides. A
    /// prop attributed to a team the other side shares a label with is
    /// attributed to nobody.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(away: awayTeam, home: homeTeam)
    }
    private var homeAbbr: String {
        homeTeam.isEmpty ? "Home" : sides.home
    }
    private var awayAbbr: String {
        awayTeam.isEmpty ? "Away" : sides.away
    }
    private var isDone: Bool { EventState.isFinished(eventStatus) }
    private var isLive: Bool { eventStatus == "live" }

    private struct PlayerCard: Identifiable {
        let id: String
        let name: String
        let initials: String
        let headshotURL: URL?
        /// #4919 — both optional, and both nil together: a card that cannot
        /// name its side prints no label and answers only the "All" filter.
        let team: String?
        let teamLabel: String?
        let color: Color
        let statGroups: [StatGroup]

        /// #4857 — the total order's key. `topProbability` is 0 for a card with
        /// no rungs, which cannot occur here (`groups` is filtered non-empty
        /// before a card is built) but keeps the key total rather than optional.
        var orderKey: PlayerPropsOrder.CardKey {
            PlayerPropsOrder.CardKey(
                rungs: statGroups.map(\.rungs.count).reduce(0, +),
                topProbability: statGroups.flatMap(\.rungs).map(\.probability).max() ?? 0,
                name: name
            )
        }
    }

    private struct StatGroup: Identifiable {
        let id: String
        let type: String
        let rungs: [Rung]

        /// #4959 — the stat's final value, stated once for the group the way the
        /// totals ladder states "Final total N" once above its rungs, rather than
        /// repeated on every rung that shares it. Every rung in a group is one
        /// player's one stat, so they carry the same served `actual`; the first
        /// one that knows answers for the group.
        var finalValue: Double? { rungs.compactMap(\.actual).first }
    }

    private struct Rung {
        let threshold: Double
        let probability: Double
        let movement: Double?
        /// #4959 — served by the endpoint on a finished event, absent otherwise.
        let actual: Double?
        let hit: Bool?
    }

    private var allPlayerCards: [PlayerCard] {
        var byPlayer: [String: [(prop: GameMarketPlayerProp, statType: String)]] = [:]
        for prop in playerProps {
            let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = parts[0].trimmingCharacters(in: .whitespaces)
            // Use the full marketName as the stat type key to prevent mixing
            // different stat categories (e.g., "Player Hits" vs "Player RBIs")
            let statType = prop.marketName.trimmingCharacters(in: .whitespaces)
            byPlayer[player, default: []].append((prop, statType))
        }

        return byPlayer.compactMap { player, props -> PlayerCard? in
            guard !props.isEmpty else { return nil }

            let initials = player.split(separator: " ")
                .compactMap { $0.first.map(String.init) }
                .prefix(2)
                .joined()

            let headshotURL = props.compactMap({ $0.prop.playerHeadshot }).first.flatMap { URL(string: $0) }
            // #4919 — the first row that KNOWS, not the first row: the served
            // `player_team` is per-prop, so a player whose opening row is
            // unattributed can still be named by a sibling. (No card on the
            // measured fixture is rescued this way, and no player's rows
            // disagree — but this is the same shape the headshot above uses,
            // and `first` would throw away an answer we were handed.)
            let side = PlayerPropsTeam.side(for: props.compactMap({ $0.prop.playerTeam }).first)
            let teamLabel = PlayerPropsTeam.label(for: side)
            let color = PlayerPropsTeam.color(for: side, home: homeColor, away: awayColor)

            var statGroups: [String: [Rung]] = [:]
            for (prop, statType) in props {
                let rung = Rung(
                    threshold: prop.threshold ?? 0,
                    probability: prop.overProbability ?? 0,
                    movement: prop.movement,
                    actual: prop.actual,
                    hit: prop.hit
                )
                statGroups[statType, default: []].append(rung)
            }

            let groups = statGroups.map { type, rungs in
                StatGroup(
                    id: "\(player)-\(type)",
                    type: type,
                    rungs: rungs.sorted { $0.threshold < $1.threshold }
                )
            }
            .filter { !$0.rungs.isEmpty }
            // #4857 — ends on the stat type, which is this level's dictionary
            // key, so two equal-length ladders cannot tie and swap on relaunch.
            .sorted {
                PlayerPropsOrder.statGroupPrecedes(
                    .init(rungs: $0.rungs.count, type: $0.type),
                    .init(rungs: $1.rungs.count, type: $1.type)
                )
            }

            guard !groups.isEmpty else { return nil }

            return PlayerCard(
                id: player,
                name: player,
                initials: initials,
                headshotURL: headshotURL,
                team: PlayerPropsTeam.filterValue(for: side),
                teamLabel: teamLabel,
                color: color,
                statGroups: groups
            )
        }
        // #4857 — ends on the player name, which is the dictionary key these
        // cards were grouped under, so the per-process iteration order can no
        // longer survive a tie and reach the screen.
        .sorted { PlayerPropsOrder.cardPrecedes($0.orderKey, $1.orderKey) }
    }

    private var filteredCards: [PlayerCard] {
        if teamFilter == "all" { return allPlayerCards }
        return allPlayerCards.filter { $0.team == teamFilter }
    }

    private var sources: [String] {
        Array(Set(playerProps.compactMap(\.source))).sorted()
    }

    var body: some View {
        let cards = filteredCards
        if allPlayerCards.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 10) {
                // Header: title + source badge + controls
                HStack {
                    Text("Player Props")
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    // Source badge — #4351: named, or not drawn.
                    if let src = SourceLabels.label(for: sources.first) {
                        Text(src)
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.1))
                            .clipShape(Capsule())
                    }

                    Spacer()
                }

                // Team filter — full width
                HStack(spacing: 0) {
                    filterButton("All", value: "all")
                        .frame(maxWidth: .infinity)
                    filterButton(homeAbbr, value: "home")
                        .frame(maxWidth: .infinity)
                    filterButton(awayAbbr, value: "away")
                        .frame(maxWidth: .infinity)
                }
                .background(Color.secondary.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))

                // Player grid — responsive columns
                let columns = [GridItem(.adaptive(minimum: 280), spacing: 10)]
                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(cards) { card in
                        playerCardView(card)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func filterButton(_ label: String, value: String) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) { teamFilter = value }
        } label: {
            Text(label)
                .font(.system(size: 11, weight: teamFilter == value ? .bold : .medium))
                .foregroundStyle(teamFilter == value ? .white : .secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(teamFilter == value ? Color.blue : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
    }

    private func playerCardView(_ card: PlayerCard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header: headshot + name + team label
            HStack(spacing: 8) {
                if let url = card.headshotURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFill()
                        case .empty:
                            // Loading state — show subtle placeholder
                            Color(card.color.opacity(0.15))
                        case .failure:
                            // Image failed to load — fall back to initials
                            Text(card.initials)
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(.white)
                        @unknown default:
                            Text(card.initials)
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(.white)
                        }
                    }
                    .frame(width: 36, height: 36)
                    .background(card.color.opacity(0.2))
                    .clipShape(Circle())
                } else {
                    Text(card.initials)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(card.color)
                        .clipShape(Circle())
                }

                VStack(alignment: .leading, spacing: 1) {
                    Text(card.name)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .lineLimit(1)
                    // #4919 — no label at all when the side is unknown.
                    if let teamLabel = card.teamLabel {
                        Text(teamLabel)
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                }

                Spacer()
            }

            // Stat groups — default to Points, per-card expansion for other stats
            let isExpanded = expandedCards.contains(card.id)
            let pointsGroups = card.statGroups.filter {
                $0.type.lowercased().contains("point") || $0.type.lowercased().contains("pts")
            }
            let defaultGroups = pointsGroups.isEmpty ? Array(card.statGroups.prefix(1)) : pointsGroups
            let groupsToShow = isExpanded ? card.statGroups : defaultGroups
            let hiddenCount = card.statGroups.count - defaultGroups.count
            if groupsToShow.count == 1 {
                statGroupView(groupsToShow[0], card: card)
            } else {
                let pairs = stride(from: 0, to: groupsToShow.count, by: 2).map { i in
                    (groupsToShow[i], i + 1 < groupsToShow.count ? groupsToShow[i + 1] : nil)
                }
                ForEach(pairs.indices, id: \.self) { idx in
                    let pair = pairs[idx]
                    HStack(alignment: .top, spacing: 10) {
                        statGroupView(pair.0, card: card)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        if let second = pair.1 {
                            statGroupView(second, card: card)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            Spacer().frame(maxWidth: .infinity)
                        }
                    }
                }
            }
            // Per-card expansion link
            if hiddenCount > 0 {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        if isExpanded {
                            expandedCards.remove(card.id)
                        } else {
                            expandedCards.insert(card.id)
                        }
                    }
                } label: {
                    Text(isExpanded ? "Show less" : "+\(hiddenCount) more stat\(hiddenCount == 1 ? "" : "s")")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.secondary.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.08), lineWidth: 1)
        )
    }

    /// Clean up stat type labels: strip "Player " prefix, keep just the stat name
    private func cleanStatLabel(_ raw: String) -> String {
        var s = raw
        // Strip common prefixes like "Player " or "Batter "
        for prefix in ["Player ", "Batter ", "Pitcher "] {
            if s.hasPrefix(prefix) {
                s = String(s.dropFirst(prefix.count))
            }
        }
        return s
    }

    private func statGroupView(_ group: StatGroup, card: PlayerCard) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(cleanStatLabel(group.type).uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
                Text(EventState.propsChanceCaption(
                    eventStatus, commenceTime: commenceTime
                ))
                    .font(.system(size: 8))
                    .foregroundStyle(.quaternary)
                    .lineLimit(1)
                // #4959 — WHAT THE STAT ACTUALLY FINISHED ON, once per group, the
                // way the totals ladder prints "Final total N" above its rungs
                // (`TotalPointsSpectrumView.finalStrip`) rather than on every row.
                // It takes layout priority over the caption because it is the fact
                // and the caption is the boilerplate: in a narrow paired column the
                // caption truncates first.
                if isDone, let final = group.finalValue {
                    Spacer(minLength: 2)
                    Text("Final \(Self.formatStatValue(final))")
                        .font(.system(size: 8, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .layoutPriority(1)
                }
            }
            ForEach(Array(group.rungs.enumerated()), id: \.offset) { _, rung in
                rungRow(rung, card: card, statType: group.type)
            }
        }
    }

    private func rungRow(_ rung: Rung, card: PlayerCard, statType: String) -> some View {
        let verdict = Self.rungVerdict(
            servedActual: rung.actual,
            servedHit: rung.hit,
            threshold: rung.threshold,
            boxActual: lookupActualValue(player: card.name, stat: statType)
        )
        let isHit = verdict.hit ?? false
        let showActual = (isDone || isLive) && verdict.hit != nil

        return HStack(spacing: 4) {
            Text("\(Int(rung.threshold))+")
                .font(.system(size: 10))
                .foregroundStyle(showActual && isHit ? card.color : .secondary)
                .fontWeight(showActual && isHit ? .bold : .regular)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(width: 28, alignment: .trailing)
                .fixedSize(horizontal: true, vertical: false)

            GeometryReader { geo in
                Capsule()
                    .fill(Color.secondary.opacity(0.08))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(isDone
                                ? (isHit ? card.color.opacity(0.5) : Color.secondary.opacity(0.15))
                                : card.color.opacity(0.3))
                            .frame(width: max(4, geo.size.width * rung.probability))
                    }
            }
            .frame(height: 8)

            if isDone, verdict.hit != nil {
                Image(systemName: isHit ? "checkmark" : "minus")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(isHit ? .green : .secondary)
                    .frame(width: 10)
            }

            Text("\(Int((rung.probability * 100).rounded()))%")
                .font(.system(size: 10, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(width: 28, alignment: .trailing)
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    private func lookupActualValue(player: String, stat: String) -> Double? {
        guard let box = boxScore else { return nil }
        return Self.actualStatValue(player: player, stat: stat, box: box)
    }

    // MARK: - Prop Verdict (pure, fail-closed)

    /// One rung's settled grade: the value the stat finished on, and whether the
    /// rung hit. `nil` for either means "no claim" — the row draws no mark.
    struct RungVerdict: Equatable {
        let actual: Double?
        let hit: Bool?
    }

    /// #4959 — RESOLVE ONE RUNG'S GRADE, SERVER FIRST.
    ///
    /// The endpoint grades a settled prop against the ESPN box score and serves
    /// `actual`/`hit` per rung; the app used to ignore both and re-derive the grade
    /// locally, which could only ever work for the five basketball stats in
    /// ``statValue(stat:in:)``'s alias table. Across 14 finished MLB games the app
    /// rendered 928 rungs, the server had graded 481 of them, and the app drew a
    /// verdict on none.
    ///
    /// Two rules, both deliberate:
    ///
    /// 1. **The served `hit` wins outright.** It is orientation-aware — the server
    ///    computes `(total < threshold)` for an Under and `(total >= threshold)` for
    ///    an Over — whereas the local fallback only ever compares `>=`. Preferring
    ///    the server therefore fixes Unders as a side effect, and collapses two
    ///    graders into one (`docs/doctrine.md`: a serve-time renderer needs every
    ///    input to travel).
    /// 2. **A served `actual` never manufactures a `hit`.** When `hit` is nil the
    ///    grade falls back to the box score EXACTLY as before — never to
    ///    `servedActual >= threshold`, because a rung whose orientation we did not
    ///    receive could be an Under, and guessing it would print a confident wrong
    ///    verdict. The number is still shown; the claim is withheld. This is the
    ///    same fail-closed instinct as ``actualStatValue(player:stat:box:)`` and as
    ///    the server's own composite-leg rule (#1728).
    ///
    /// Live and scheduled payloads carry neither key, so the box-score path is
    /// untouched for in-progress games.
    static func rungVerdict(
        servedActual: Double?,
        servedHit: Bool?,
        threshold: Double,
        boxActual: Double?
    ) -> RungVerdict {
        let actual = servedActual ?? boxActual
        if let servedHit {
            return RungVerdict(actual: actual, hit: servedHit)
        }
        guard let boxActual else {
            return RungVerdict(actual: actual, hit: nil)
        }
        return RungVerdict(actual: actual, hit: boxActual >= threshold)
    }

    /// A stat line reads as a whole number when it is one ("2", not "2.0"), and
    /// keeps its fraction when it has one, so a `0.5`-threshold stat is never
    /// rounded into a different answer.
    static func formatStatValue(_ value: Double) -> String {
        value.rounded() == value
            ? String(Int(value))
            : String(format: "%g", value)
    }

    // MARK: - Prop Attribution (pure, fail-closed)

    /// Grade a prop against the box score by EXACT normalized full-name identity.
    ///
    /// The old logic matched on last-name substring containment and returned the
    /// first dictionary hit, so duplicate surnames, suffixes ("Jr."), and substrings
    /// could attribute another player's line — and dictionary iteration made the
    /// wrong grade unstable (C43 P1). Until stable player IDs exist we fail closed:
    /// grade only when EXACTLY ONE box-score row normalizes to the prop's player
    /// name; zero or multiple matches return nil (ungraded), never a guess.
    static func actualStatValue(player: String, stat: String, box: [String: [String: Double]]) -> Double? {
        let target = normalizedPlayerName(player)
        guard !target.isEmpty else { return nil }
        let matches = box.keys.filter { normalizedPlayerName($0) == target }
        // Exactly one identity, or no grade.
        guard matches.count == 1, let key = matches.first, let stats = box[key] else { return nil }
        return statValue(stat: stat, in: stats)
    }

    /// Normalize a player name for identity comparison: lowercase, strip periods and
    /// commas (so "A.J." == "AJ"), collapse whitespace. Suffixes ("Jr.", "III") are
    /// deliberately kept as distinct tokens — "Michael Porter" and "Michael Porter Jr."
    /// are different people, so they must NOT collide into one match.
    static func normalizedPlayerName(_ raw: String) -> String {
        raw.lowercased()
            .replacingOccurrences(of: ".", with: "")
            .replacingOccurrences(of: ",", with: "")
            .components(separatedBy: .whitespaces)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    /// Resolve a stat value once a unique player identity is established. Direct key,
    /// then a small alias map (matches the prior behavior; only reached after identity).
    static func statValue(stat: String, in stats: [String: Double]) -> Double? {
        let statKey = stat.lowercased()
        if let val = stats[statKey] { return val }
        let mapping: [String: [String]] = [
            "points": ["points", "pts"],
            "rebounds": ["rebounds", "reb", "totalRebounds"],
            "assists": ["assists", "ast"],
            "steals": ["steals", "stl"],
            "three pointers": ["threePointersMade", "3pm", "threePointers"],
        ]
        for (statName, aliases) in mapping {
            if statKey.contains(statName) || statName.contains(statKey) {
                for alias in aliases {
                    if let val = stats[alias] { return val }
                }
            }
        }
        return nil
    }
}
