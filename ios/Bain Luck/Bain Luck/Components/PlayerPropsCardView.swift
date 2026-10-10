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
    /// #6866 — the crests a TEAM's own ladder card draws (`Team Sacks`,
    /// `Team Total Yards`), in place of the letter a player without a photo
    /// gets. nil keeps the old letter: `TeamLogoView` still climbs its ESPN
    /// rung by name, so an absent url is not an absent crest.
    var homeLogoURL: String? = nil
    var awayLogoURL: String? = nil
    var sportKey: String? = nil

    @State private var teamFilter: String = "all"
    /// #5176 — the fields opened past their first ``PlayerPropsField/visibleCount`` legs.
    @State private var expandedFields: Set<String> = []
    /// #10830 — the target the reader picked on each pre-game ladder, by
    /// ladder id. Absent means the ladder's default (``PlayerPropsFamily/defaultTarget(probabilities:)``).
    @State private var selectedTargets: [String: Double] = [:]
    /// Alex 10/10 — the protected-touchdown ladder whose rule sheet is open.
    @State private var openRule: PropItem?

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
    /// #10830 — only a game that has not started browses by target. Live and
    /// finished ladders keep the rung renderer, which carries the live hit
    /// colouring and the served verdicts.
    private var browsesByTarget: Bool { !isDone && !isLive }

    private struct PlayerCard: Identifiable {
        let id: String
        let name: String
        let initials: String
        let headshotURL: URL?
        /// #6866 — set only when the card's subject is PROVEN to be one of this
        /// game's two teams (``PlayerPropsTeam/teamSubjectSide(subject:marketName:homeTeam:awayTeam:)``):
        /// that team's full name, so the header draws its crest. nil for every
        /// player and for any team name the rule could not pin to one side.
        let crestTeam: String?
        /// #4919 — both optional, and both nil together: a card that cannot
        /// name its side prints no label and answers only the "All" filter.
        let team: String?
        let teamLabel: String?
        let color: Color
        let statGroups: [StatGroup]

        /// #5137 — the ladders that are showing a price, and the ladders that
        /// are only showing the same number over and over. Every part of the
        /// card that speaks to the reader in probabilities reads the first list.
        var pricedGroups: [StatGroup] { statGroups.filter(\.isPriced) }
        var unpricedGroups: [StatGroup] { statGroups.filter { !$0.isPriced } }

        /// #4857 — the total order's key, over the priced ladders only (#5137).
        ///
        /// A card is placed by what it can tell a reader, so a flat ladder must
        /// not buy it a rung count or lend it a `topProbability`: Gausman's six
        /// rungs of 0.80 would otherwise rank his card above every genuinely
        /// priced one on the page on the strength of a number no market quoted.
        /// `topProbability` is 0 for a card with no priced rungs — 4 of the 627
        /// measured — which sorts it last, where a card with nothing to show
        /// belongs.
        var orderKey: PlayerPropsOrder.CardKey {
            let priced = pricedGroups
            return PlayerPropsOrder.CardKey(
                rungs: priced.map(\.rungs.count).reduce(0, +),
                topProbability: priced.flatMap(\.rungs).map(\.probability).max() ?? 0,
                name: name
            )
        }
    }

    private struct StatGroup: Identifiable {
        let id: String
        let type: String
        let rungs: [Rung]
        /// The venues that quoted this ladder (Alex 10/10: a protection rule
        /// is read for ONE venue's contract).
        var sources: Set<String> = []

        /// #5137 — a ladder whose every rung prints the same percentage is not a
        /// price and does not draw bars. See ``PlayerPropsPricing``.
        var isPriced: Bool {
            PlayerPropsPricing.isPricedLadder(rungs.map(\.probability))
        }

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
        /// #4577 — where this market opened, on the same OVER axis as
        /// ``probability``. nil on 47% of measured rungs; those draw no tick.
        let pregameMark: Double?
        /// #10830 — did a venue price this rung at all? `probability` is 0 as
        /// geometry for one that did not, and a target chip must not print it.
        var priced: Bool = true
    }

    /// #10830 — one player's one ladder, as a row of the props browser.
    private struct PropItem: Identifiable {
        let id: String
        let card: PlayerCard
        let group: StatGroup
        let family: String
        let statLabel: String
        /// Alex 10/10 — what the row PRINTS for the stat. The venue's own
        /// words (`statLabel`) except for a verified protected contract, whose
        /// row says what it counts and offers the rule on tap.
        var displayStat: String
        var protectedRule: Bool = false
    }

    /// Every ladder on the page as a browser row: the PRICED ladders under
    /// their stat's family, the unpriced ones under ``PlayerPropsFamily/unpricedFamily``
    /// (#5137 — a flat ladder never takes a stat's place). Cards keep their
    /// #4857 order inside each family; families are dealt by
    /// ``PlayerPropsFamily/orderedFamilies(_:)``.
    private func browseItems(_ cards: [PlayerCard]) -> [PropItem] {
        let items: [PropItem] = cards.flatMap { card -> [PropItem] in
            let priced = card.pricedGroups.map { group -> PropItem in
                let label = cleanStatLabel(group.type, player: card.name)
                let isProtected = isVerifiedProtected(group, statLabel: label)
                return PropItem(id: group.id, card: card, group: group,
                                family: isProtected
                                    ? PlayerPropsFamily.protectedTouchdownFamily
                                    : PlayerPropsFamily.family(statLabel: label, isPriced: true),
                                statLabel: label,
                                displayStat: displayStat(group, card: card),
                                protectedRule: isProtected)
            }
            let unpriced = card.unpricedGroups.map { group -> PropItem in
                let label = cleanStatLabel(group.type, player: card.name)
                return PropItem(id: group.id, card: card, group: group,
                                family: PlayerPropsFamily.family(statLabel: label, isPriced: false),
                                statLabel: label,
                                displayStat: displayStat(group, card: card),
                                protectedRule: isVerifiedProtected(group, statLabel: label))
            }
            return priced + unpriced
        }
        let order = PlayerPropsFamily.orderedFamilies(items.map(\.family))
        let rank = Dictionary(uniqueKeysWithValues: order.enumerated().map { ($1, $0) })
        return items.enumerated()
            .sorted { a, b in
                let (ra, rb) = (rank[a.element.family] ?? 0, rank[b.element.family] ?? 0)
                return ra != rb ? ra < rb : a.offset < b.offset
            }
            .map(\.element)
    }

    private var allPlayerCards: [PlayerCard] {
        var byPlayer: [String: [(prop: GameMarketPlayerProp, statType: String)]] = [:]
        for prop in playerProps {
            let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            // #9148 — "SEA Seahawks D/ST" is named "Seahawks D/ST".
            let player = PropSubject.display(parts[0].trimmingCharacters(in: .whitespaces))
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
            let servedSide = PlayerPropsTeam.side(for: props.compactMap({ $0.prop.playerTeam }).first)
            // #6866 — a team's own ladders arrive with no `player_team` at all.
            // Only consulted when the server named no side, so a served side is
            // never overruled; the first row that PROVES a team wins, like above.
            let subjectSide: PlayerPropsTeam.Side = props.lazy
                .map { PlayerPropsTeam.teamSubjectSide(
                    subject: player,
                    marketName: $0.prop.marketName,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam
                ) }
                .first { $0 != .unknown } ?? .unknown
            let side = servedSide != .unknown ? servedSide : subjectSide
            let crestTeam: String? = switch subjectSide {
            case .home: homeTeam
            case .away: awayTeam
            case .unknown: nil
            }
            let teamLabel = PlayerPropsTeam.label(for: side)
            let color = PlayerPropsTeam.color(for: side, home: homeColor, away: awayColor)

            var statGroups: [String: [Rung]] = [:]
            var statSources: [String: Set<String>] = [:]
            for (prop, statType) in props {
                if let source = prop.source { statSources[statType, default: []].insert(source) }
                let rung = Rung(
                    threshold: prop.threshold ?? 0,
                    probability: prop.overProbability ?? 0,
                    movement: prop.movement,
                    actual: prop.actual,
                    hit: prop.hit,
                    pregameMark: prop.pregameMark,
                    priced: prop.overProbability != nil
                )
                statGroups[statType, default: []].append(rung)
            }

            let groups = statGroups.map { type, rungs in
                StatGroup(
                    id: "\(player)-\(type)",
                    type: type,
                    rungs: rungs.sorted { $0.threshold < $1.threshold },
                    sources: statSources[type] ?? []
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
                crestTeam: crestTeam,
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
        // #5176 — a page whose only props are fields still draws the card.
        let fields = PlayerPropsField.fields(from: playerProps)
        if allPlayerCards.isEmpty && fields.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 10) {
                // Header: title + source badge + controls
                HStack {
                    Text("Player Props")
                        .font(.headline)
                        .accessibilityAddTraits(.isHeader)

                    // Source badge — #4351: named, or not drawn.
                    if let src = SourceLabels.label(for: sources.first) {
                        Text(src)
                            .font(.caption2.weight(.heavy))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.blue.opacity(0.1))
                            .clipShape(Capsule())
                    }

                    Spacer()
                }

                // #5176 — the game's fields sit above the team filter because
                // the filter does not narrow them: "most in the game" is about
                // both sides.
                if !fields.isEmpty {
                    let columns = [GridItem(.adaptive(minimum: 280), spacing: 10)]
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(fields) { field in
                            fieldView(field)
                        }
                    }
                }

                if !allPlayerCards.isEmpty {
                    // Team filter — full width
                    HStack(spacing: 0) {
                        filterButton("All", value: "all")
                            .frame(maxWidth: .infinity)
                        filterButton(homeAbbr, value: "home")
                            .frame(maxWidth: .infinity)
                        filterButton(awayAbbr, value: "away")
                            .frame(maxWidth: .infinity)
                    }
                    .padding(2)
                    .background(Color.secondary.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                    // #10830 — every ladder, browsable by stat family and
                    // searchable by player, in a bounded window (web #10809).
                    MarketBrowserView(
                        label: "Player props",
                        items: browseItems(cards),
                        group: \.family,
                        searchText: { "\($0.card.name) \($0.card.teamLabel ?? "") \($0.statLabel) \($0.displayStat)" },
                        searchPrompt: "player or stat"
                    ) { item in
                        propRow(item)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .sheet(item: $openRule) { item in
                participationRuleSheet(item)
            }
        }
    }

    /// Alex 10/10: the team filter's whole third is the button. It used to be
    /// a word-sized 11pt pill inside a full-width frame drawn OUTSIDE the
    /// button, so a tap beside the word landed on nothing. The frame, the
    /// 44pt height and the content shape are now all inside the label.
    private func filterButton(_ label: String, value: String) -> some View {
        let isActive = teamFilter == value
        return Button {
            withAnimation(.easeInOut(duration: 0.15)) { teamFilter = value }
        } label: {
            Text(label)
                .font(.subheadline.weight(isActive ? .semibold : .medium))
                .lineLimit(1)
                .minimumScaleFactor(0.85)
                .foregroundStyle(isActive ? .white : .secondary)
                .padding(.horizontal, 10)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(isActive ? Color.blue : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .contentShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("props-team-filter")
        .accessibilityAddTraits(isActive ? .isSelected : [])
    }

    // MARK: - One ladder as a browser row (#10830)

    /// The player, then the ladder. Before the game the ladder is browsed by
    /// target (``targetRow(_:)``); live and after it, the rung renderer keeps
    /// every grade it carries (#4959 served verdicts, #4907 live hits). An
    /// unpriced ladder never draws a price in either (#5137).
    private func propRow(_ item: PropItem) -> some View {
        let target = item.group.isPriced && browsesByTarget ? selectedTarget(item) : nil
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 10) {
                playerAvatar(item.card, size: 32)
                VStack(alignment: .leading, spacing: 1) {
                    Text(item.card.name)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    // #4919 — no side label at all when the side is unknown.
                    Text(rowSubtitle(item, target: target?.rung))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if let target {
                    Text("\(PlayerPropsPricing.displayPercent(target.rung.probability))%")
                        .font(.title3.weight(.bold))
                        .monospacedDigit()
                }
            }
            .accessibilityElement(children: .combine)

            // The rule control sits at the end of the target row where it has
            // room, so a page of protected ladders is not a page of rule lines.
            if item.protectedRule && !(item.group.isPriced && browsesByTarget) {
                participationRuleButton(item, compact: false)
            }

            if !item.group.isPriced {
                unpricedGroupView(item.group, card: item.card)
            } else if browsesByTarget {
                HStack(alignment: .center, spacing: 8) {
                    targetRow(item, chosen: target?.index)
                    if item.protectedRule {
                        participationRuleButton(item, compact: true)
                    }
                }
            } else {
                statGroupView(item.group, card: item.card)
            }
        }
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.barTrack.opacity(0.5)).frame(height: 0.5)
        }
    }

    /// Crest for a team's own ladder (#6866), headshot for a player, initials
    /// when there is neither.
    @ViewBuilder
    private func playerAvatar(_ card: PlayerCard, size: CGFloat) -> some View {
        if let crestTeam = card.crestTeam {
            TeamLogoView(
                url: crestTeam == homeTeam ? homeLogoURL : awayLogoURL,
                teamName: crestTeam,
                color: card.color,
                size: size,
                sportKey: sportKey,
                opponentName: crestTeam == homeTeam ? awayTeam : homeTeam
            )
            .accessibilityHidden(true)
        } else if let url = card.headshotURL {
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
            .frame(width: size, height: size)
            .background(card.color.opacity(0.2))
            .clipShape(Circle())
            .accessibilityHidden(true)
        } else {
            Text(card.initials)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(card.color)
                .clipShape(Circle())
                .accessibilityHidden(true)
        }
    }

    /// The rung a pre-game ladder shows: the reader's pick while it is still a
    /// priced rung, otherwise the priced rung nearest even odds. nil when no
    /// rung carries a price — then nothing is selected and no number printed.
    private func selectedTarget(_ item: PropItem) -> (index: Int, rung: Rung)? {
        let rungs = item.group.rungs
        let fallback = PlayerPropsFamily.defaultTarget(
            probabilities: rungs.map { $0.priced ? $0.probability : nil }
        )
        let chosen = selectedTargets[item.group.id].flatMap { threshold in
            rungs.firstIndex { $0.threshold == threshold && $0.priced }
        } ?? fallback
        return chosen.map { ($0, rungs[$0]) }
    }

    /// "Touchdowns · 1+ · Home" — the stat, the chosen line (pre-game only)
    /// and the side when it is known (#4919).
    private func rowSubtitle(_ item: PropItem, target: Rung?) -> String {
        var parts = [item.displayStat]
        if let target { parts.append(PlayerPropsFamily.targetLabel(target.threshold)) }
        if let side = item.card.teamLabel { parts.append(side) }
        return parts.joined(separator: " · ")
    }

    /// A pre-game ladder browsed by TARGET: one chip per quoted line, each
    /// filled to its own price; the chosen line's chance sits in the row's
    /// header. Every number is a quoted rung's; an unpriced rung's chip carries
    /// no fill and is never the one selected.
    private func targetRow(_ item: PropItem, chosen: Int?) -> some View {
        let rungs = item.group.rungs
        let selected = chosen.map { rungs[$0] }

        return VStack(alignment: .leading, spacing: 8) {
            if rungs.count > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(Array(rungs.enumerated()), id: \.offset) { index, rung in
                            targetChip(rung, isSelected: index == chosen, item: item)
                        }
                    }
                    .padding(.vertical, 1)
                }
                .accessibilityLabel("\(spokenStat(item)) targets")
            } else if let selected {
                GeometryReader { geo in
                    Capsule()
                        .fill(Color.secondary.opacity(0.08))
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(item.card.color.opacity(0.45))
                                .frame(width: max(4, geo.size.width * selected.probability))
                        }
                }
                .frame(height: 8)
                .accessibilityHidden(true)
            }
        }
    }

    private func targetChip(_ rung: Rung, isSelected: Bool, item: PropItem) -> some View {
        let label = PlayerPropsFamily.targetLabel(rung.threshold)
        let percent = PlayerPropsPricing.displayPercent(rung.probability)
        return Button {
            guard rung.priced else { return }
            selectedTargets[item.group.id] = rung.threshold
        } label: {
            Text(label)
                .font(.subheadline.weight(isSelected ? .bold : .regular))
                .monospacedDigit()
                .foregroundStyle(isSelected ? Color.primary : Color.secondary)
                .padding(.horizontal, 10)
                .frame(minWidth: 52, minHeight: 44)
                .background(alignment: .bottom) {
                    if rung.priced {
                        GeometryReader { geo in
                            VStack(spacing: 0) {
                                Spacer(minLength: 0)
                                Rectangle()
                                    .fill(item.card.color.opacity(0.18))
                                    .frame(height: geo.size.height * min(max(rung.probability, 0), 1))
                            }
                        }
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? item.card.color : Color.barTrack,
                                lineWidth: isSelected ? 1.5 : 0.5)
                )
        }
        .buttonStyle(.plain)
        .disabled(!rung.priced)
        .accessibilityLabel(rung.priced
            ? "\(label) \(spokenStat(item)), \(percent)%"
            : "\(label) \(spokenStat(item)), not priced")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    /// #5113 — the stat name, with any prefix the reader can already see
    /// stripped. Display only: `group.type` remains the served `marketName` and
    /// is still the grouping key.
    private func cleanStatLabel(_ raw: String, player: String?) -> String {
        PlayerPropsStatLabel.display(
            marketName: raw,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            player: player
        )
    }

    /// Alex 10/10 — a verified protected-touchdown ladder (Kalshi, NFL).
    private func isVerifiedProtected(_ group: StatGroup, statLabel: String) -> Bool {
        PlayerPropsFamily.isVerifiedProtectedTouchdowns(
            statLabel: statLabel, sportKey: sportKey, sources: group.sources)
    }

    /// The stat as a row prints it. Display only: `group.type` stays the
    /// grouping and grading key.
    private func displayStat(_ group: StatGroup, card: PlayerCard) -> String {
        let label = cleanStatLabel(group.type, player: card.name)
        return isVerifiedProtected(group, statLabel: label)
            ? PlayerPropsFamily.protectedTouchdownStat
            : label
    }

    /// The stat as VoiceOver says it — a protected contract says so.
    private func spokenStat(_ item: PropItem) -> String {
        item.protectedRule ? "\(item.displayStat), protected" : item.displayStat
    }

    private func participationRuleButton(_ item: PropItem, compact: Bool) -> some View {
        Button {
            openRule = item
        } label: {
            Label(compact ? "Rule" : PlayerPropsFamily.participationRuleTitle, systemImage: "info.circle")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.blue)
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, compact ? 6 : 0)
                .padding(.trailing, compact ? 0 : 12)
                .frame(minWidth: 44, minHeight: 44, alignment: compact ? .center : .leading)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(PlayerPropsFamily.participationRuleTitle)
        .accessibilityHint("Explains how this protected touchdown market settles")
    }

    private func participationRuleSheet(_ item: PropItem) -> some View {
        NavigationStack {
            List {
                Section {
                    ForEach(PlayerPropsFamily.participationRuleLines, id: \.self) { line in
                        Text(line)
                            .font(.body)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Section("Market") {
                    Text("\(item.card.name) · \(item.group.type)")
                        .font(.subheadline)
                    Link("Kalshi's full contract terms",
                         destination: PlayerPropsFamily.participationRuleTermsURL)
                        .font(.subheadline)
                }
            }
            .navigationTitle(PlayerPropsFamily.participationRuleTitle)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { openRule = nil }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func statGroupView(_ group: StatGroup, card: PlayerCard) -> some View {
        // #6826 — DOES ANY RUNG UNDER THIS CAPTION CARRY A VERDICT? The caption
        // labels the rungs directly beneath it, so it is answered on the group,
        // by the same `verdict(for:)` that draws the ✓/– — never by the status
        // alone and never by a second grading rule. On a live or scheduled game
        // the caption ignores this value; it is computed honestly rather than
        // stubbed so the argument never carries a claim the rungs do not.
        let hasGradedRung = group.rungs.contains {
            verdict(for: $0, card: card, statType: group.type).hit != nil
        }

        return VStack(alignment: .leading, spacing: 3) {
            // #4959 — WHAT THE STAT ACTUALLY FINISHED ON, once per group, the
            // way the totals ladder prints "Final total N" above its rungs
            // (`TotalPointsSpectrumView.finalStrip`) rather than on every row.
            // #10076 — the header never clips the stat name for the caption: in
            // a narrow paired column the caption drops to its own line.
            PropsStatGroupHeader(
                label: displayStat(group, card: card).uppercased(),
                caption: EventState.propsChanceCaption(
                    eventStatus, commenceTime: commenceTime, hasGradedRung: hasGradedRung
                ),
                finalText: isDone ? group.finalValue.map { "Final \(Self.formatStatValue($0))" } : nil
            )
            ForEach(Array(group.rungs.enumerated()), id: \.offset) { _, rung in
                rungRow(rung, card: card, statType: group.type)
            }
        }
    }

    // MARK: - Fields (#5176)

    /// One "Most …" market: its phrase, then a row per player, likeliest first
    /// (the leader first once graded). Past ``PlayerPropsField/visibleCount``
    /// legs the rest sit behind "+N more".
    private func fieldView(_ field: PlayerPropsField.Field) -> some View {
        let isOpen = expandedFields.contains(field.id)
        let shown = isOpen
            ? field.candidates
            : Array(field.candidates.prefix(PlayerPropsField.visibleCount))
        let hiddenCount = field.candidates.count - PlayerPropsField.visibleCount

        return VStack(alignment: .leading, spacing: 3) {
            PropsStatGroupHeader(
                label: field.title.uppercased(),
                caption: PlayerPropsField.caption(
                    eventStatus: eventStatus,
                    commenceTime: commenceTime,
                    isGraded: field.isGraded
                )
            )
            ForEach(shown, id: \.name) { candidate in
                fieldRow(candidate)
            }
            if hiddenCount > 0 {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        if isOpen {
                            expandedFields.remove(field.id)
                        } else {
                            expandedFields.insert(field.id)
                        }
                    }
                } label: {
                    Text(isOpen ? "Show less" : "+\(hiddenCount) more")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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

    /// One player in a field, drawn in the rung's vocabulary — track, pregame
    /// tick, ✓/– once graded, percentage — with the name where the threshold
    /// goes. No team colour: the served legs name no side.
    private func fieldRow(_ candidate: PlayerPropsField.Candidate) -> some View {
        let graded = isDone && candidate.hit != nil
        let led = candidate.hit == true

        return HStack(spacing: 4) {
            Text(candidate.name)
                .font(.system(size: 10))
                .foregroundStyle(graded && led ? .primary : .secondary)
                .fontWeight(graded && led ? .bold : .regular)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, alignment: .leading)

            GeometryReader { geo in
                Capsule()
                    .fill(Color.secondary.opacity(0.08))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(isDone
                                ? (led ? Color.blue.opacity(0.5) : Color.secondary.opacity(0.15))
                                : Color.blue.opacity(0.3))
                            .frame(width: max(4, geo.size.width * candidate.probability))
                    }
                    .overlay(alignment: .leading) {
                        if let fraction = PlayerPropsScript.tickFraction(
                            pregameMark: candidate.pregameMark,
                            isFinished: isDone
                        ) {
                            Capsule()
                                .fill(Color.primary.opacity(0.45))
                                .frame(width: Self.pregameTickWidth)
                                .offset(x: PlayerPropsScript.tickOffset(
                                    fraction: fraction,
                                    trackWidth: geo.size.width,
                                    tickWidth: Self.pregameTickWidth
                                ))
                        }
                    }
            }
            .frame(width: 96, height: 8)

            if graded {
                Image(systemName: led ? "checkmark" : "minus")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(led ? .green : .secondary)
                    .frame(width: 10)
            }

            Text("\(PlayerPropsPricing.displayPercent(candidate.probability))%")
                .font(.system(size: 10, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(width: 28, alignment: .trailing)
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    // MARK: - Unpriced ladders (#5137)

    /// One unpriced ladder: its name, what the stat finished on, and the rungs
    /// that were graded.
    ///
    /// **A rung earns a row here by having something to say.** The priced ladder
    /// gives a rung a bar and a percentage, and neither survives the judgement
    /// that this ladder is not a price — so an ungraded rung would be a bare
    /// "3+" with empty space beside it, which is the shape D34 rules out: if a
    /// number cannot be shown honestly the space is left empty rather than
    /// filled with something that merely occupies it. 203 of the 286 flat rungs
    /// measured ARE graded, so this is the common case, not the fallback; a
    /// ladder with nothing graded shows its name alone and says the true thing
    /// by saying less.
    private func unpricedGroupView(_ group: StatGroup, card: PlayerCard) -> some View {
        let graded = isDone
            ? group.rungs.filter { verdict(for: $0, card: card, statType: group.type).hit != nil }
            : []

        return VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(displayStat(group, card: card).uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
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
            ForEach(Array(graded.enumerated()), id: \.offset) { _, rung in
                unpricedRungRow(rung, card: card, statType: group.type)
            }
        }
    }

    /// One graded rung of an unpriced ladder: the threshold and the verdict. No
    /// bar, no percentage — there is no price to draw.
    private func unpricedRungRow(_ rung: Rung, card: PlayerCard, statType: String) -> some View {
        let isHit = verdict(for: rung, card: card, statType: statType).hit ?? false

        return HStack(spacing: 4) {
            Text("\(Int(rung.threshold))+")
                .font(.system(size: 10))
                .foregroundStyle(isHit ? card.color : .secondary)
                .fontWeight(isHit ? .bold : .regular)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(width: 28, alignment: .trailing)
                .fixedSize(horizontal: true, vertical: false)

            Image(systemName: isHit ? "checkmark" : "minus")
                .font(.system(size: 7, weight: .bold))
                .foregroundStyle(isHit ? .green : .secondary)
                .frame(width: 10)

            Spacer(minLength: 0)
        }
    }

    /// One rung's grade, resolved the way every row on this card resolves it.
    private func verdict(for rung: Rung, card: PlayerCard, statType: String) -> RungVerdict {
        Self.rungVerdict(
            servedActual: rung.actual,
            servedHit: rung.hit,
            threshold: rung.threshold,
            boxActual: lookupActualValue(player: card.name, stat: statType)
        )
    }

    /// #4577 — the pregame tick's width. 2pt reads as a mark rather than a
    /// second fill at the 8pt track height, and is the width the offset maths is
    /// clamped against, so the view and ``PlayerPropsScript`` cannot disagree
    /// about where the track ends.
    static let pregameTickWidth: CGFloat = 2

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
                    // #4577 — THE SCRIPT's tick: where this market opened. Drawn
                    // OVER the fill, because the interesting case is a market
                    // that has moved up and would otherwise bury its own
                    // baseline. See ``PlayerPropsScript`` for why there is no
                    // caption and no fallback.
                    .overlay(alignment: .leading) {
                        if let fraction = PlayerPropsScript.tickFraction(
                            pregameMark: rung.pregameMark,
                            isFinished: isDone
                        ) {
                            Capsule()
                                .fill(Color.primary.opacity(0.45))
                                .frame(width: Self.pregameTickWidth)
                                .offset(x: PlayerPropsScript.tickOffset(
                                    fraction: fraction,
                                    trackWidth: geo.size.width,
                                    tickWidth: Self.pregameTickWidth
                                ))
                        }
                    }
            }
            .frame(height: 8)

            if isDone, verdict.hit != nil {
                Image(systemName: isHit ? "checkmark" : "minus")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(isHit ? .green : .secondary)
                    .frame(width: 10)
            }

            // #5137 — through the same rounding the flat-ladder rule reads, so a
            // ladder judged flat is exactly a ladder printing one repeated number.
            Text("\(PlayerPropsPricing.displayPercent(rung.probability))%")
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
