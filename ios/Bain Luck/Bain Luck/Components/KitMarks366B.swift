import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Preloaded Artwork Environment Seam (tests & previews only)

private struct KitPreloadedImagesKey366B: EnvironmentKey {
    static let defaultValue: [URL: PlatformImage] = [:]
}

extension EnvironmentValues {
    var kitPreloadedImages366B: [URL: PlatformImage] {
        get { self[KitPreloadedImagesKey366B.self] }
        set { self[KitPreloadedImagesKey366B.self] = newValue }
    }
}

// MARK: - Mark Dispatcher

/// Renders one of the 8 shared Kit v1 marks purely from its geometric payload.
struct KitMarkView366B: View {
    let mark: KitV1Mark

    var body: some View {
        switch mark {
        case .picture(let m):
            KitPictureMarkView366B(mark: m)
        case .word(let m):
            KitWordMarkView366B(mark: m)
        case .number(let m):
            KitNumberMarkView366B(mark: m)
        case .bar(let m):
            KitBarMarkView366B(mark: m)
        case .tile(let m):
            KitTileMarkView366B(mark: m)
        case .ring(let m):
            KitRingMarkView366B(mark: m)
        case .dot(let m):
            KitDotMarkView366B(mark: m)
        case .line(let m):
            KitLineMarkView366B(mark: m)
        }
    }
}

// MARK: - 1. Picture Mark

struct KitPictureMarkView366B: View {
    let mark: KitV1PictureMark

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.kitPreloadedImages366B) private var preloadedImages
    @State private var loadedImage: PlatformImage?

    private var dimension: CGFloat {
        switch mark.size ?? .sm {
        case .xs: return 18
        case .sm: return 24
        case .md: return 32
        }
    }

    private var resolvedURL: URL? {
        guard KitV1PictureMark.isAllowedHTTPSURL(mark.url) else { return nil }
        return URL(string: mark.url.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private var activeImage: PlatformImage? {
        if let loadedImage { return loadedImage }
        if let url = resolvedURL, let preloaded = preloadedImages[url] { return preloaded }
        return nil
    }

    private var isPortraitCrop: Bool {
        mark.contain == false || mark.subjectKind == "person"
    }

    var body: some View {
        let size = dimension
        let radius = mark.subjectKind == "flag" ? 3 : (isPortraitCrop ? size / 2 : size * 0.22)
        Group {
            if let img = activeImage {
                if isPortraitCrop {
                    Image(platformImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: size, height: size)
                        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
                } else {
                    let darkBacking = colorScheme == .dark
                        && mark.subjectKind == "team"
                        && TeamLogoView.needsDarkSurfaceBacking(img)
                    ZStack {
                        if darkBacking {
                            Circle().fill(Color.white.opacity(0.92))
                        }
                        Image(platformImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .padding(darkBacking ? size * 0.10 : 0)
                    }
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
                }
            } else {
                fallbackBadge(size: size, radius: radius)
            }
        }
        .accessibilityLabel(mark.alt)
        .task(id: mark.url) {
            guard activeImage == nil, let url = resolvedURL else { return }
            loadedImage = await ImageCache.shared.image(for: url)
        }
    }

    private func fallbackBadge(size: CGFloat, radius: CGFloat) -> some View {
        let symbolName: String? = {
            switch mark.subjectKind {
            case "person": return "person.fill"
            case "flag": return "flag.fill"
            case "team": return nil
            default: return "photo"
            }
        }()
        return RoundedRectangle(cornerRadius: radius, style: .continuous)
            .fill(KitTones366B.elevatedBackground(for: colorScheme))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
            )
            .overlay {
                if let symbolName {
                    Image(systemName: symbolName)
                        .font(.system(size: max(9, size * 0.44), weight: .semibold))
                        .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                } else {
                    Text(TeamLogoView.badge(teamName: mark.alt, opponentName: nil))
                        .font(.system(size: max(8, size * 0.36), weight: .bold))
                        .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                }
            }
            .frame(width: size, height: size)
    }
}

// MARK: - 2. Word Mark

struct KitWordMarkView366B: View {
    let mark: KitV1WordMark

    @Environment(\.colorScheme) private var colorScheme

    private var textAlignment: TextAlignment {
        switch mark.align ?? .left {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    private var frameAlignment: Alignment {
        switch mark.align ?? .left {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    var body: some View {
        let baseColor = KitTones366B.textColor(for: mark.tone, scheme: colorScheme)
        Group {
            switch mark.style ?? .row {
            case .heroLabel:
                VStack(alignment: .leading, spacing: 2) {
                    Text(mark.text)
                        .font(.subheadline.weight(mark.bold == false ? .medium : .bold))
                        .foregroundStyle(baseColor)
                        .fixedSize(horizontal: false, vertical: true)
                    if let secondary = mark.secondaryText, !secondary.isEmpty {
                        Text(secondary)
                            .font(.caption)
                            .foregroundStyle(KitTones366B.textColor(for: .secondary, scheme: colorScheme))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)

            case .meta:
                VStack(alignment: (mark.align == .right) ? .trailing : ((mark.align == .center) ? .center : .leading), spacing: 1) {
                    Text(mark.text)
                        .font(.caption2.weight(mark.bold == true ? .semibold : .medium))
                        .foregroundStyle(baseColor)
                        .fixedSize(horizontal: false, vertical: true)
                    if let secondary = mark.secondaryText, !secondary.isEmpty {
                        Text(secondary)
                            .font(.caption2)
                            .foregroundStyle(KitTones366B.textColor(for: .muted, scheme: colorScheme))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(minWidth: fixedMinWidth, maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)

            case .pill:
                Text(mark.text)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(baseColor)
                    .multilineTextAlignment(textAlignment)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .frame(maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(KitTones366B.elevatedBackground(for: colorScheme))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(KitTones366B.cardBorder(for: colorScheme), lineWidth: 1)
                    )

            case .kicker:
                let kickerColor = mark.tone == nil
                    ? KitTones366B.brandAccent(for: colorScheme)
                    : KitTones366B.textColor(for: mark.tone, scheme: colorScheme)
                Text(mark.text.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(kickerColor)
                    .fixedSize(horizontal: false, vertical: true)

            case .rank:
                Text(mark.text)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(KitTones366B.textColor(for: mark.tone ?? .muted, scheme: colorScheme))
                    .fixedSize(horizontal: true, vertical: false)

            case .sub, .row:
                let font: Font = (mark.style == .sub)
                    ? .caption.weight(mark.bold == true ? .semibold : .regular)
                    : .subheadline.weight(mark.bold == true ? .semibold : .regular)
                Text(mark.text)
                    .font(font)
                    .foregroundStyle(baseColor)
                    .multilineTextAlignment(textAlignment)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minWidth: fixedMinWidth, maxWidth: mark.width == .flex ? .infinity : nil, alignment: frameAlignment)
            }
        }
    }

    private var fixedMinWidth: CGFloat? {
        switch mark.width {
        case .xs: return 34
        case .sm: return 68
        case .md: return 88
        case .flex, .auto, nil: return nil
        }
    }
}

// MARK: - 3. Number Mark

struct KitNumberMarkView366B: View {
    let mark: KitV1NumberMark

    @Environment(\.colorScheme) private var colorScheme

    private var frameAlignment: Alignment {
        switch mark.align ?? .right {
        case .left: return .leading
        case .center: return .center
        case .right: return .trailing
        }
    }

    private var font: Font {
        switch mark.prominence ?? .primary {
        case .hero:
            return .title.weight(.heavy).monospacedDigit()
        case .primary:
            return (mark.unit == .oneInN)
                ? .subheadline.weight(.heavy).monospacedDigit()
                : .subheadline.weight(.bold).monospacedDigit()
        case .cell:
            return .footnote.weight(.bold).monospacedDigit()
        case .secondary:
            return .caption.weight(.semibold).monospacedDigit()
        }
    }

    private var minWidth: CGFloat? {
        switch mark.width {
        case .xs: return 36
        case .sm: return 42
        case .md: return 56
        case .flex, .auto, nil: return nil
        }
    }

    var body: some View {
        Text(mark.display)
            .font(font)
            .foregroundStyle(KitTones366B.textColor(for: mark.tone, scheme: colorScheme))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .frame(minWidth: minWidth, alignment: frameAlignment)
    }
}

// MARK: - 4. Bar Mark (Single, Split, Range)

struct KitBarMarkView366B: View {
    let mark: KitV1BarMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        switch mark.barStyle {
        case .split:
            splitBar
        case .range:
            rangeBar
        case .single:
            singleBar
        }
    }

    private var singleBar: some View {
        let clamped = min(1.0, max(0.03, mark.fill ?? 0.0))
        let fillColor = KitTones366B.barColor(
            hex: mark.fillColor?.light,
            darkHex: mark.fillColorDark ?? mark.fillColor?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        let targetWidth: CGFloat? = {
            switch mark.width {
            case .xs: return 40
            case .sm: return 56
            case .md: return 74
            case .flex, .auto, nil: return nil
            }
        }()
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(KitTones366B.trackBackground(for: colorScheme))
                Capsule()
                    .fill(fillColor)
                    .frame(width: max(4, geo.size.width * clamped))
            }
        }
        .frame(width: targetWidth, height: mark.width == .md ? 9 : 8)
        .frame(maxWidth: targetWidth == nil ? .infinity : targetWidth)
    }

    @ViewBuilder
    private var splitBar: some View {
        let segs = mark.segments ?? []
        if segs.count == 2 {
            let pair = KitTones366B.splitBarColors(
                leftHex: segs[0].color?.light,
                leftDarkHex: segs[0].colorDark ?? segs[0].color?.dark,
                rightHex: segs[1].color?.light,
                rightDarkHex: segs[1].colorDark ?? segs[1].color?.dark,
                scheme: colorScheme
            )
            GeometryReader { geo in
                let total = max(0.001, segs[0].fill + segs[1].fill)
                let leftFrac = min(0.95, max(0.05, segs[0].fill / total))
                HStack(spacing: 1) {
                    Rectangle().fill(pair.left).frame(width: max(3, (geo.size.width - 1) * leftFrac))
                    Rectangle().fill(pair.right)
                }
                .clipShape(Capsule())
            }
            .frame(height: 9)
            .frame(maxWidth: .infinity)
        } else {
            GeometryReader { geo in
                let total = max(0.001, segs.reduce(0.0) { $0 + max(0.0, $1.fill) })
                HStack(spacing: 1) {
                    ForEach(Array(segs.enumerated()), id: \.offset) { idx, seg in
                        let frac = max(0.0, seg.fill) / total
                        Rectangle()
                            .fill(KitTones366B.barColor(
                                hex: seg.color?.light,
                                darkHex: seg.colorDark ?? seg.color?.dark,
                                fallbackIndex: idx,
                                scheme: colorScheme
                            ))
                            .frame(width: max(2, geo.size.width * frac))
                    }
                }
                .clipShape(Capsule())
            }
            .frame(height: 9)
            .frame(maxWidth: .infinity)
        }
    }

    private var rangeBar: some View {
        let lo = min(1.0, max(0.0, mark.lo ?? 0.0))
        let hi = min(1.0, max(lo, mark.hi ?? lo))
        let accent = KitTones366B.barColor(
            hex: mark.fillColor?.light,
            darkHex: mark.fillColorDark ?? mark.fillColor?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        return GeometryReader { geo in
            let leftX = geo.size.width * lo
            let spanW = max(12, geo.size.width * (hi - lo))
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(KitTones366B.trackBackground(for: colorScheme))
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(accent.opacity(0.26))
                    .overlay(
                        Text(mark.pctLabel ?? "")
                            .font(.caption2.weight(.bold).monospacedDigit())
                            .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
                    )
                    .frame(width: min(geo.size.width - leftX, spanW), height: 18)
                    .offset(x: leftX)
            }
        }
        .frame(height: 20)
        .frame(maxWidth: .infinity)
    }
}

// MARK: - 5. Tile Mark

struct KitTileMarkView366B: View {
    let mark: KitV1TileMark
    var compact: Bool = false

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let palette = KitTones366B.tilePalette(
            shade: mark.shade,
            highlightRole: mark.highlightRole,
            muted: mark.muted ?? false,
            scheme: colorScheme
        )
        VStack(spacing: 2) {
            if let top = mark.topLabel, !top.isEmpty {
                Text(top)
                    .font(.system(size: compact ? 9.5 : 10.5, weight: .medium))
                    .foregroundStyle(palette.secondaryForeground)
                    .minimumScaleFactor(0.85)
                    .lineLimit(1)
            }
            Text(mark.centerLabel)
                .font((compact ? Font.caption : Font.footnote).weight(.bold).monospacedDigit())
                .foregroundStyle(palette.foreground)
                .minimumScaleFactor(0.85)
                .lineLimit(1)
            if let bottom = mark.bottomLabel, !bottom.isEmpty {
                Text(bottom)
                    .font(.system(size: compact ? 9.5 : 10.5, weight: .semibold).monospacedDigit())
                    .foregroundStyle(palette.secondaryForeground)
                    .minimumScaleFactor(0.8)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, compact ? 2 : 6)
        .padding(.vertical, compact ? 5 : 6)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(palette.background)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(palette.border, lineWidth: 1)
        )
    }
}

// MARK: - 6. Ring Mark

struct KitRingMarkView366B: View {
    let mark: KitV1RingMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let clamped = min(1.0, max(0.0, mark.progress))
        let pct = Int((clamped * 100.0).rounded())
        let strokeColor = mark.tone == .muted
            ? DS.textMuted
            : KitTones366B.brandAccent(for: colorScheme)
        ZStack {
            Circle()
                .stroke(KitTones366B.trackBackground(for: colorScheme), lineWidth: 3)
            Circle()
                .trim(from: 0, to: clamped)
                .stroke(strokeColor, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(mark.label ?? "\(pct)%")
                .font(.caption2.weight(.bold).monospacedDigit())
                .foregroundStyle(KitTones366B.textColor(for: .primary, scheme: colorScheme))
        }
        .frame(width: 30, height: 30)
    }
}

// MARK: - 7. Dot Mark

struct KitDotMarkView366B: View {
    let mark: KitV1DotMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let dotColor = KitTones366B.barColor(
            hex: mark.color?.light,
            darkHex: mark.colorDark ?? mark.color?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        Group {
            if let pic = mark.picture {
                KitPictureMarkView366B(mark: pic)
            } else {
                Circle()
                    .fill(dotColor)
                    .overlay(Circle().stroke(KitTones366B.cardBackground(for: colorScheme), lineWidth: 1.5))
                    .frame(width: 10, height: 10)
            }
        }
        .accessibilityLabel(mark.label)
    }
}

// MARK: - 8. Line Mark

struct KitLineMarkView366B: View {
    let mark: KitV1LineMark

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let strokeColor = KitTones366B.barColor(
            hex: mark.color?.light,
            darkHex: mark.colorDark ?? mark.color?.dark,
            fallbackIndex: 0,
            scheme: colorScheme
        )
        GeometryReader { geo in
            let pts = mark.points
            if pts.count >= 2 {
                let minX = pts.map(\.x).min() ?? 0
                let maxX = max(minX + 0.0001, pts.map(\.x).max() ?? 1)
                let minY = pts.map(\.y).min() ?? 0
                let maxY = max(minY + 0.0001, pts.map(\.y).max() ?? 1)
                Path { path in
                    for (idx, pt) in pts.enumerated() {
                        let px = CGFloat((pt.x - minX) / (maxX - minX)) * geo.size.width
                        let py = (1 - CGFloat((pt.y - minY) / (maxY - minY))) * geo.size.height
                        if idx == 0 {
                            path.move(to: CGPoint(x: px, y: py))
                        } else {
                            path.addLine(to: CGPoint(x: px, y: py))
                        }
                    }
                }
                .stroke(
                    strokeColor,
                    style: StrokeStyle(
                        lineWidth: 2,
                        lineCap: .round,
                        lineJoin: .round,
                        dash: mark.dashed == true ? [4, 3] : []
                    )
                )
            }
        }
        .frame(height: 36)
    }
}
