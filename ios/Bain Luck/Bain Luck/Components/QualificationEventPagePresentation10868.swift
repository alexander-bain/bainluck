import SwiftUI

// #10868 — the INDEPENDENT-QUALIFICATION UNAVAILABLE presentation: a set of
// independent qualification props ("will this entrant qualify?") whose
// retained capture the OWNER has admitted as holding no recorded trade, no
// probability history and no confirmed result. Several entrants can qualify:
// these are separate props, never shares of one winner. A fan sees, in this
// order: the owner's qualification label and title with a small About
// control, the owner's absence headline and lines, the owner's line that more
// than one entrant can qualify, and ONE entry to every prop. The catalogue is
// a readable grid of the props in the owner's order (or the owner's window of
// it) with the owner's ordering context and an Overview action. One prop shows
// its own outcome words and predicate, the owner's absence, pre-event and
// result words, its rules verbatim and its own source and capture context. The
// About is the owner's text with the exact catalogue entry.
//
// Presentation only, from the approved native "Quiet" alternative (the
// selected `QualificationQuiet.swift`, its browser twin and its adoption
// note). NOT ported: the reference's capture decoder, its exact no-trade
// predicate, its alphabetical sort, the browser's fixed-size pager, its capture
// date formatter, its sheet / catalogue session and its raw-record disclosure.
// All of that is the owner's. This file never reads a price, a volume, a
// status, a result, a count or a clock; it holds no chance slot at all, so no
// zero (or any other figure) can become a chance here.
//
// WHY NOT THE GENERIC FIELD PAGE: `FieldEventPagePresentation10868` always
// mounts its probability-history anchor and its phase headline of contenders'
// chances, needs an explicit event phase and a story stream, and has no
// validity mode; its "All props" card face and its Details always print a
// reading slot with a chart marker, and its result line exists only in the
// mode that pairs it with a hollow pre-event marker. None of that may appear
// for a capture with no recorded probability.
//
// WHAT IS REUSED, unchanged:
//   • `OriginalMarketDetails9483.Catalogue` / `Original` / `Identity` /
//     `Selection` — the owner's ONE canonical catalogue and held selection, the
//     shape every #10868 "All props" already receives;
//   • `OriginalMarketDetails9483.original(in:selection:)` and
//     `content(catalogue:selection:)` — exact-identity resolution: a nil,
//     blank, out-of-scope, withdrawn or duplicated identity is no prop, never
//     a neighbour, never the About;
//   • `OriginalMarketDetails9483.rules(_:)` — rules verbatim, blank
//     paragraphs dropped;
//   • `OriginalMarketChooser9483.choices` / `action` / `spoken` — every row's
//     owner label, exact selection, held mark and unavailable status, and the
//     only way a row acts;
//   • `OriginalMarketCatalogue9483.geometry` — the catalogue's adaptive
//     columns (one column at accessibility sizes), here behind a local Layout
//     because the catalogue's own Layout is private to its file and its card
//     face prints a chance slot;
//   • `FieldEventPagePresentation10868.held` / `heldAction` — the once-only
//     hold before a page or catalogue action;
//   • `FieldEventPageAboutContent10868` — the owner's About text.
//
// Read from each `Original`: identity, title (the predicate), outcome (the
// entrant's own words) and `about.source` / `about.rules` /
// `about.provenance`. Never read: its mode, either reading, its grade or its
// historical quote.
//
// VALIDITY: the owner's explicit `QualificationEventPageValidity10868`. While
// invalidated, every mode shows only the owner's invalidated words — nothing
// of the old overview, catalogue, prop or About, and no action — and the
// host's own Done/Back path is untouched. A held selection that is omitted, or
// that does not resolve to exactly one original in the catalogue's scope,
// shows the owner's prop-unavailable words: never the About, never a
// neighbour, and never the invalidated words.
//
// ACTIONS: the overview's About control and its one entry, and the
// catalogue's Overview action, page links and rows call the owner's
// interaction hook once and then the exact callback with its exact value. The
// prop and About content (the host's full reader) keep the exact callbacks.
// Without a callback there is no control and no hook call; building or
// laying out the view calls nothing.
//
// LAYOUT: plain content for the host's scroll. Every action is at least 44pt
// tall; every label wraps whole and is never truncated; the grid reflows to
// one column at large and accessibility sizes; essential words are body or
// headline sized.
//
// The host owns the scroll, sheets, navigation, Back/Done, focus, routing to
// and from every mode, the held selection, held and received frames, the
// ranked stream, any disclosure, live subscriptions and every genuine update.
// This view keeps no state, runs no timer or animation, holds no subscription
// and presents nothing of its own.

/// What the host's container is showing, chosen by the host.
nonisolated enum QualificationEventPageMode10868: Equatable, CaseIterable {
    /// Label, title, About control, absence, meaning and the one entry.
    case overview
    /// Every prop in the owner's order, or the owner's window of it.
    case catalogue
    /// The held selection's prop.
    case prop
    /// The owner's About.
    case about
}

/// The owner's explicit standing for the retained capture this page
/// describes — never inferred here from a price, a volume, a status, a result,
/// a count or a clock.
nonisolated enum QualificationEventPageValidity10868: Equatable {
    /// Admitted by the owner for the snapshot shown.
    case qualified
    /// The owner has withdrawn that admission: nothing of the old capture shows.
    case invalidated
}

/// The owner's words for a state with nothing else to show.
nonisolated struct QualificationEventPageNotice10868: Equatable {
    let title: String
    /// Nil draws none.
    let words: String?
}

/// The owner's words for the overview, also heading the catalogue.
nonisolated struct QualificationEventPageOverview10868: Equatable {
    /// The qualification label above the title; nil draws none.
    let eyebrow: String?
    let title: String
    /// Spoken name of the About control; the control shows only with a callback.
    let aboutLabel: String
    /// The absence headline.
    let headline: String
    /// The lines under it, in order.
    let absence: [String]
    /// The independent-outcome meaning.
    let meaning: String
    /// The one entry to every prop; shown only with a callback.
    let allPropsLabel: String
    var aboutHint: String? = nil
}

/// The owner's words for the catalogue.
nonisolated struct QualificationEventPageBrowse10868: Equatable {
    /// The return to the overview; shown only with a callback.
    let overviewLabel: String
    let heading: String
    /// The owner's ordering context; nil draws none.
    let context: String?
    /// Spoken name of the grid.
    let gridLabel: String
    /// A row with no readable label of its own.
    let unavailableChoice: String
}

/// The owner's words for one prop.
nonisolated struct QualificationEventPagePropCopy10868: Equatable {
    /// The prop's absence headline.
    let headline: String
    /// The absence, pre-event and result lines, in order.
    let absence: [String]
    let rulesLabel: String
    let sourceLabel: String
    /// The owner's capture context below the rules; nil draws none.
    let note: String?
}

/// One owner page link, handed back by its opaque id.
nonisolated struct QualificationEventPagePageLink10868: Equatable {
    let id: String
    let label: String
}

/// The owner's window of the catalogue: which rows show, in its order, and
/// its page words and links. Rows only REFER to catalogue identities.
struct QualificationEventPageWindow10868: Equatable {
    let rows: [OriginalMarketDetails9483.Identity]
    /// The owner's position words for this window; blank draws none.
    let label: String
    /// Nil: no earlier window and no control.
    let previous: QualificationEventPagePageLink10868?
    /// Nil: no later window and no control.
    let next: QualificationEventPagePageLink10868?
}

struct QualificationEventPageInput10868: Equatable {
    let validity: QualificationEventPageValidity10868
    /// The owner's one canonical catalogue, in the owner's order.
    let catalogue: OriginalMarketDetails9483.Catalogue
    /// The owner's row label for an exact identity; otherwise its title.
    let labels: [OriginalMarketDetails9483.Identity: String]
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    let overview: QualificationEventPageOverview10868
    let browse: QualificationEventPageBrowse10868
    let prop: QualificationEventPagePropCopy10868
    let about: FieldEventPageAbout10868
    /// The About's catalogue entry; nil draws none.
    let aboutCatalogueLabel: String?
    /// The overview and catalogue while invalidated.
    let invalidatedPage: QualificationEventPageNotice10868
    /// The prop and About while invalidated.
    let invalidatedDetails: QualificationEventPageNotice10868
    /// A held selection that is omitted or does not resolve.
    let propUnavailable: QualificationEventPageNotice10868
    /// The owner's window; nil shows every original.
    var window: QualificationEventPageWindow10868? = nil
}

/// One prop as shown, all from its own original.
struct QualificationEventPageProp10868: Equatable {
    let selection: OriginalMarketDetails9483.Selection
    /// The original's outcome words.
    let name: String
    /// The original's title.
    let predicate: String
    let rules: OriginalMarketDetails9483.Rules
    let source: String?
    let provenance: [LadderOriginalProbabilityDetails9483.Row]
}

nonisolated enum QualificationEventPageAccessibilityID10868 {
    static let overview = "qualificationEventPage10868.overview"
    static let about = "qualificationEventPage10868.about"
    static let allProps = "qualificationEventPage10868.allProps"
    static let catalogue = "qualificationEventPage10868.catalogue"
    static let back = "qualificationEventPage10868.catalogue.overview"
    static let previous = "qualificationEventPage10868.catalogue.previous"
    static let next = "qualificationEventPage10868.catalogue.next"
    static let grid = "qualificationEventPage10868.catalogue.grid"
    static let prop = "qualificationEventPage10868.prop"
    static let aboutContent = "qualificationEventPage10868.aboutContent"
    static let aboutCatalogue = "qualificationEventPage10868.aboutContent.catalogue"
    static let invalidated = "qualificationEventPage10868.invalidated"
    static let propUnavailable = "qualificationEventPage10868.prop.unavailable"
}

// MARK: - Model

/// What each mode shows, resolved from the owner's input alone.
struct QualificationEventPageModel10868: Equatable {
    typealias Details = OriginalMarketDetails9483
    typealias Chooser = OriginalMarketChooser9483

    enum Unavailable: Equatable {
        /// No held selection.
        case omitted
        /// A held selection that is not exactly one original in scope.
        case unresolved
    }

    enum PropResolution: Equatable {
        case shown(QualificationEventPageProp10868)
        case unavailable(Unavailable)
    }

    enum Content: Equatable {
        case invalidated(QualificationEventPageNotice10868)
        case overview
        case catalogue
        case prop(QualificationEventPageProp10868)
        case propUnavailable(Unavailable)
        case about
    }

    let input: QualificationEventPageInput10868

    init(_ input: QualificationEventPageInput10868) {
        self.input = input
    }

    var isQualified: Bool { input.validity == .qualified }

    func content(_ mode: QualificationEventPageMode10868) -> Content {
        guard isQualified else {
            switch mode {
            case .overview, .catalogue: return .invalidated(input.invalidatedPage)
            case .prop, .about: return .invalidated(input.invalidatedDetails)
            }
        }
        switch mode {
        case .overview: return .overview
        case .catalogue: return .catalogue
        case .about: return .about
        case .prop:
            switch prop {
            case .shown(let prop): return .prop(prop)
            case .unavailable(let reason): return .propUnavailable(reason)
            }
        }
    }

    /// The held selection's prop through the Details resolver — so exactly
    /// the props a row can open. The window never limits it.
    var prop: PropResolution {
        guard let selection = input.selection else { return .unavailable(.omitted) }
        guard Details.content(catalogue: input.catalogue, selection: selection) != nil,
              let original = Details.original(in: input.catalogue, selection: selection)
        else { return .unavailable(.unresolved) }
        return .shown(QualificationEventPageProp10868(
            selection: selection,
            name: original.outcome,
            predicate: original.title,
            rules: Details.rules(original.about.rules),
            source: Self.readable(original.about.source),
            provenance: original.about.provenance.filter {
                Self.readable($0.label) != nil && Self.readable($0.value) != nil
            }))
    }

    /// The rows the catalogue shows, in the owner's order: the owner's window,
    /// else every original. A window row that is not exactly one catalogue
    /// original keeps the owner's label (or the unavailable words), says it is
    /// unavailable and has no selection.
    var choices: [Chooser.Choice] {
        let all = Chooser.choices(catalogue: input.catalogue, selection: input.selection,
                                  labels: input.labels, unavailableChoice: input.browse.unavailableChoice)
        guard let window = input.window else { return all }
        let originals = input.catalogue.originals
        return window.rows.map { identity in
            let matches = originals.indices.filter { originals[$0].identity == identity }
            if matches.count == 1 { return all[matches[0]] }
            let own = Self.readable(input.labels[identity])
            return Chooser.Choice(label: own ?? Self.readable(input.browse.unavailableChoice) ?? Chooser.unavailableStatus,
                                  selection: nil, isSelected: false,
                                  status: own == nil ? nil : Chooser.unavailableStatus)
        }
    }

    var pageLabel: String? { Self.readable(input.window?.label) }
    var previous: QualificationEventPagePageLink10868? { Self.link(input.window?.previous) }
    var next: QualificationEventPagePageLink10868? { Self.link(input.window?.next) }

    /// The heading region's words, in reading order.
    var headerWords: [String] {
        let overview = input.overview
        return [Self.readable(overview.eyebrow), Self.readable(overview.title), Self.readable(overview.headline)]
            .compactMap { $0 } + Self.lines(overview.absence) + [Self.readable(overview.meaning)].compactMap { $0 }
    }

    /// A prop's words, in reading order.
    func words(_ prop: QualificationEventPageProp10868) -> [String] {
        let copy = input.prop
        var words = [Self.readable(prop.name), Self.readable(prop.predicate), Self.readable(copy.headline)]
            .compactMap { $0 } + Self.lines(copy.absence)
        switch prop.rules {
        case .verified(let paragraphs): words += [copy.rulesLabel] + paragraphs
        case .unavailable(let reason): words += [copy.rulesLabel, reason]
        case .omitted: break
        }
        if let source = prop.source { words += [copy.sourceLabel, source] }
        words += prop.provenance.flatMap { [$0.label, $0.value] }
        if let note = Self.readable(copy.note) { words.append(note) }
        return words
    }

    /// The About text's words, as `FieldEventPageAboutContent10868` draws them.
    var aboutWords: [String] {
        [Self.readable(input.about.title)].compactMap { $0 } + Self.lines(input.about.paragraphs)
    }

    static func words(_ notice: QualificationEventPageNotice10868) -> [String] {
        [readable(notice.title), readable(notice.words)].compactMap { $0 }
    }

    static func lines(_ lines: [String]) -> [String] {
        lines.compactMap { readable($0) }
    }

    static func link(_ link: QualificationEventPagePageLink10868?) -> QualificationEventPagePageLink10868? {
        guard let link, readable(link.id) != nil, readable(link.label) != nil else { return nil }
        return link
    }

    static func readable(_ words: String?) -> String? {
        FieldEventPageModel10868.readable(words)
    }
}

// MARK: - View

struct QualificationEventPagePresentation10868: View {
    typealias Model = QualificationEventPageModel10868
    typealias Chooser = OriginalMarketChooser9483
    typealias ID = QualificationEventPageAccessibilityID10868

    let input: QualificationEventPageInput10868
    var mode: QualificationEventPageMode10868 = .overview
    /// Opens the host's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's catalogue.
    var onCatalogue: (() -> Void)? = nil
    /// Returns the host's catalogue to the overview.
    var onOverview: (() -> Void)? = nil
    /// The owner's exact page id.
    var onPage: ((String) -> Void)? = nil
    /// A row's exact selection, for the host to hold and route.
    var onSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// Called once just before an overview or catalogue action reaches its
    /// callback. Never called by building the view or by prop/About content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var minimumCardWidth = OriginalMarketCatalogue9483.minimumCardWidth

    var model: Model { Model(input) }

    /// The overview and the catalogue carry the heading and its About control.
    private var showsHeading: Bool { mode == .overview || mode == .catalogue }

    // MARK: Actions — each exactly what its control runs

    /// The heading's About control, after the hook.
    func aboutAction() -> (() -> Void)? {
        guard model.isQualified, showsHeading else { return nil }
        return FieldEventPagePresentation10868.heldAction(onAbout, by: onInteraction)
    }

    /// The overview's one entry, after the hook.
    func allPropsAction() -> (() -> Void)? {
        guard model.isQualified, mode == .overview, Model.readable(input.overview.allPropsLabel) != nil else { return nil }
        return FieldEventPagePresentation10868.heldAction(onCatalogue, by: onInteraction)
    }

    /// The catalogue's Overview action, after the hook.
    func overviewAction() -> (() -> Void)? {
        guard model.isQualified, mode == .catalogue, Model.readable(input.browse.overviewLabel) != nil else { return nil }
        return FieldEventPagePresentation10868.heldAction(onOverview, by: onInteraction)
    }

    /// One of the model's own page links, after the hook, with its exact id.
    func pageAction(_ link: QualificationEventPagePageLink10868?) -> (() -> Void)? {
        guard model.isQualified, mode == .catalogue, let link = Model.link(link),
              link == model.previous || link == model.next,
              let action = FieldEventPagePresentation10868.held(onPage, by: onInteraction) else { return nil }
        return { action(link.id) }
    }

    /// A row's exact selection, after the hook; nil for a row that cannot open.
    func selectAction(_ choice: Chooser.Choice) -> (() -> Void)? {
        guard model.isQualified, mode == .catalogue else { return nil }
        return Chooser.action(choice, onSelect: FieldEventPagePresentation10868.held(onSelect, by: onInteraction))
    }

    /// The About's catalogue entry: the exact callback, no hook.
    func aboutCatalogueAction() -> (() -> Void)? {
        guard model.isQualified, mode == .about, Model.readable(input.aboutCatalogueLabel) != nil else { return nil }
        return onCatalogue
    }

    /// Every word the mode draws, in reading order — the same values the body
    /// draws, entries included only where their control shows.
    func shownWords() -> [String] {
        switch model.content(mode) {
        case .invalidated(let notice):
            return Model.words(notice)
        case .overview:
            return model.headerWords + (allPropsAction() == nil ? [] : [input.overview.allPropsLabel])
        case .catalogue:
            var words = model.headerWords
            if overviewAction() != nil { words.append(input.browse.overviewLabel) }
            words += [Model.readable(input.browse.heading), Model.readable(input.browse.context)].compactMap { $0 }
            if pageAction(model.previous) != nil, let link = model.previous { words.append(link.label) }
            if let label = model.pageLabel { words.append(label) }
            if pageAction(model.next) != nil, let link = model.next { words.append(link.label) }
            return words + model.choices.flatMap { [$0.label] + ($0.status.map { [$0] } ?? []) }
        case .prop(let prop):
            return model.words(prop)
        case .propUnavailable:
            return Model.words(input.propUnavailable)
        case .about:
            return model.aboutWords + (aboutCatalogueAction() == nil ? [] : [input.aboutCatalogueLabel ?? ""])
        }
    }

    // MARK: Body

    var body: some View {
        Group {
            switch model.content(mode) {
            case .invalidated(let notice): noticeView(notice, id: ID.invalidated)
            case .overview: overview
            case .catalogue: catalogue
            case .prop(let prop): propContent(prop)
            case .propUnavailable: noticeView(input.propUnavailable, id: ID.propUnavailable)
            case .about: aboutContent
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
            if let action = allPropsAction() {
                Divider()
                Button(action: action) {
                    QualificationEventPageRow10868(label: input.overview.allPropsLabel, style: .entry)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(ID.allProps)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(QualificationEventPageSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.overview)
    }

    /// The owner's label, title and About control, then the absence and the
    /// independent-outcome meaning.
    private var header: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    if let eyebrow = Model.readable(input.overview.eyebrow) {
                        Text(eyebrow)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                    }
                    Text(input.overview.title)
                        .font(.title.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.isHeader)
                if let action = aboutAction() {
                    Button(action: action) {
                        Image(systemName: "info.circle")
                            .font(.title3)
                            .foregroundStyle(DS.textPrimary)
                            .frame(minWidth: QualificationEventPageRow10868.minimumHeight,
                                   minHeight: QualificationEventPageRow10868.minimumHeight)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(input.overview.aboutLabel)
                    .accessibilityHint(input.overview.aboutHint ?? "")
                    .accessibilityIdentifier(ID.about)
                }
            }
            VStack(alignment: .leading, spacing: 8) {
                Text(input.overview.headline)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                ForEach(Array(Model.lines(input.overview.absence).enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(.body)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            Text(input.overview.meaning)
                .font(.body)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var catalogue: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(QualificationEventPageSurface10868())
            VStack(alignment: .leading, spacing: 12) {
                if let action = overviewAction() {
                    Button(action: action) {
                        Label {
                            Text(input.browse.overviewLabel)
                        } icon: {
                            Image(systemName: "chevron.left")
                        }
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: QualificationEventPageRow10868.minimumHeight)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(ID.back)
                }
                Text(input.browse.heading)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let context = Model.readable(input.browse.context) {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if model.pageLabel != nil || pageAction(model.previous) != nil || pageAction(model.next) != nil {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) {
                            pageControl(model.previous, systemImage: "chevron.left", id: ID.previous)
                            Spacer(minLength: 8)
                            pageLabelText
                            Spacer(minLength: 8)
                            pageControl(model.next, systemImage: "chevron.right", id: ID.next)
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            pageLabelText
                            pageControl(model.previous, systemImage: "chevron.left", id: ID.previous)
                            pageControl(model.next, systemImage: "chevron.right", id: ID.next)
                        }
                    }
                }
                QualificationEventPageGrid10868(minimumCardWidth: minimumCardWidth,
                                                spacing: OriginalMarketCatalogue9483.spacing,
                                                accessibilitySize: typeSize.isAccessibilitySize) {
                    ForEach(Array(model.choices.enumerated()), id: \.offset) { _, choice in
                        row(choice)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.browse.gridLabel)
                .accessibilityIdentifier(ID.grid)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.catalogue)
    }

    @ViewBuilder private var pageLabelText: some View {
        if let label = model.pageLabel {
            Text(label)
                .font(.body.monospacedDigit())
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func pageControl(_ link: QualificationEventPagePageLink10868?, systemImage: String,
                                          id: String) -> some View {
        if let link, let action = pageAction(link) {
            Button(action: action) {
                Label {
                    Text(link.label)
                } icon: {
                    Image(systemName: systemImage)
                }
                .font(.body.weight(.semibold))
                .foregroundStyle(DS.blue)
                .frame(minWidth: QualificationEventPageRow10868.minimumHeight,
                       minHeight: QualificationEventPageRow10868.minimumHeight)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }

    /// A row that opens is a button running exactly `selectAction`; a row that
    /// cannot is static, keeps its label and says it is unavailable.
    @ViewBuilder private func row(_ choice: Chooser.Choice) -> some View {
        if let action = selectAction(choice) {
            Button(action: action) {
                QualificationEventPageRow10868(label: choice.label, status: choice.status, acts: true,
                                               selected: choice.isSelected)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Chooser.spoken(choice))
            .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        } else {
            QualificationEventPageRow10868(label: choice.label, status: choice.status, acts: false,
                                           selected: choice.isSelected)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Chooser.spoken(choice))
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        }
    }

    /// One prop, all from its own original and the owner's words.
    private func propContent(_ prop: QualificationEventPageProp10868) -> some View {
        let copy = input.prop
        return VStack(alignment: .leading, spacing: 16) {
            Text(prop.name)
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            Text(prop.predicate)
                .font(.body)
                .foregroundStyle(DS.textPrimary)
            VStack(alignment: .leading, spacing: 6) {
                Text(copy.headline)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                ForEach(Array(Model.lines(copy.absence).enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(.body)
                        .foregroundStyle(DS.textPrimary)
                }
            }
            switch prop.rules {
            case .verified(let paragraphs):
                VStack(alignment: .leading, spacing: 8) {
                    caption(copy.rulesLabel)
                    ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                        Text(paragraph)
                            .font(.body)
                            .foregroundStyle(DS.textPrimary)
                    }
                }
            case .unavailable(let reason):
                VStack(alignment: .leading, spacing: 4) {
                    caption(copy.rulesLabel)
                    Text(reason)
                        .font(.body)
                        .foregroundStyle(DS.textPrimary)
                }
            case .omitted:
                EmptyView()
            }
            if let source = prop.source {
                fact(copy.sourceLabel, source)
            }
            ForEach(Array(prop.provenance.enumerated()), id: \.offset) { _, row in
                fact(row.label, row.value)
            }
            if let note = Model.readable(copy.note) {
                Text(note)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.prop)
    }

    private func caption(_ label: String) -> some View {
        Text(label)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DS.textSecondary)
            .accessibilityAddTraits(.isHeader)
    }

    private func fact(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            caption(label)
            Text(value)
                .font(.body)
                .foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    private var aboutContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            FieldEventPageAboutContent10868(about: input.about)
            if let action = aboutCatalogueAction(), let label = input.aboutCatalogueLabel {
                Button(action: action) {
                    QualificationEventPageRow10868(label: label, style: .entry)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(ID.aboutCatalogue)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ID.aboutContent)
    }

    private func noticeView(_ notice: QualificationEventPageNotice10868, id: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(notice.title)
                .font(.title3.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let words = Model.readable(notice.words) {
                Text(words)
                    .font(.body)
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(id)
    }
}

// MARK: - Row face and grid

/// One action's face: the whole label (it wraps, never truncates), the
/// unavailable status when it cannot open, and a chevron only when it acts.
/// At least 44pt tall at every text size.
struct QualificationEventPageRow10868: View {
    enum Style: Equatable {
        /// A grid card that fills its row's height.
        case card
        /// A full-width text entry.
        case entry
    }

    let label: String
    var status: String? = nil
    var acts: Bool = true
    var selected: Bool = false
    var style: Style = .card

    static let minimumHeight: CGFloat = 44

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
        HStack(alignment: .center, spacing: 8) {
            if selected {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(DS.blue)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(style == .entry ? .body.weight(.semibold) : .headline)
                    .foregroundStyle(style == .entry ? DS.blue : (acts ? DS.textPrimary : DS.textSecondary))
                if let status {
                    Text(status)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if acts {
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(style == .entry ? DS.blue : DS.textSecondary)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, style == .card ? 12 : 0)
        .padding(.vertical, style == .card ? 10 : 4)
        .frame(maxWidth: .infinity, minHeight: Self.minimumHeight,
               maxHeight: style == .card ? .infinity : nil, alignment: .leading)
        .background(shape.fill(style == .card ? (selected ? DS.blue.opacity(0.10) : DS.surface) : Color.clear))
        .overlay(shape.strokeBorder(style == .card && selected ? DS.blue : Color.clear, lineWidth: 2))
        .contentShape(Rectangle())
    }
}

/// Equal columns at the width actually offered, counted by the existing
/// `OriginalMarketCatalogue9483.geometry`; each row is as tall as its tallest
/// face and every face fills that height. No scrolling of its own.
struct QualificationEventPageGrid10868: Layout {
    let minimumCardWidth: CGFloat
    let spacing: CGFloat
    let accessibilitySize: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let (geometry, rows) = measure(proposal.width, subviews)
        return CGSize(width: geometry.width, height: geometry.stack(rows.map(\.height)).total)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (geometry, rows) = measure(bounds.width, subviews)
        let xs = geometry.stack(Array(repeating: geometry.cardWidth, count: geometry.columns)).origins
        let ys = geometry.stack(rows.map(\.height)).origins
        for (row, y) in zip(rows, ys) {
            for (index, x) in zip(row.indices, xs) {
                subviews[index].place(at: CGPoint(x: bounds.minX + x, y: bounds.minY + y), anchor: .topLeading,
                                      proposal: ProposedViewSize(width: geometry.cardWidth, height: row.height))
            }
        }
    }

    private struct Row {
        let indices: Range<Int>
        let height: CGFloat
    }

    private func measure(_ offered: CGFloat?, _ subviews: Subviews) -> (OriginalMarketCatalogue9483.Geometry, [Row]) {
        let geometry = OriginalMarketCatalogue9483.geometry(
            cards: subviews.count, width: offered,
            intrinsicWidth: subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0,
            minimumCardWidth: minimumCardWidth, spacing: spacing, accessibilitySize: accessibilitySize)
        let proposal = ProposedViewSize(width: geometry.cardWidth, height: nil)
        let rows = geometry.rows(count: subviews.count).map { indices in
            let height = indices.map { OriginalMarketCatalogue9483.length(subviews[$0].sizeThatFits(proposal).height) ?? 0 }
                .max() ?? 0
            return Row(indices: indices, height: height)
        }
        return (geometry, rows)
    }
}

/// The page's card on the page surface.
private struct QualificationEventPageSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
