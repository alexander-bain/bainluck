import SwiftUI

/// #10090 (Alex 67) — the event page's heartbeat ("EKG"), drawn under the big
/// percentage on a live game.
///
/// Whether it beats is decided in `EkgHeartbeat` from evidence only (the
/// markets reporting in); this draws the answer. A beat traces the line once
/// (keyed on the beat count) and leaves it faint; no report for 15 s draws a
/// flat line. Reduce Motion gets a still dot and "Updated Ns ago" instead.
/// The page wraps it in the button that opens the existing details popover.
struct EkgHeartbeatView: View {
    let tracker: EkgTracker
    let status: LiveUpdateStatus
    /// The page's pinned clock in tests; otherwise the 1 s tick, so the line
    /// goes flat without waiting for a new frame.
    var asOf: Date? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let presentation = EkgHeartbeat.present(tracker, status: status, now: asOf ?? context.date)
            Self.drawn(EkgHeartbeat.drawing(presentation, reduceMotion: reduceMotion))
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(presentation.label)
                .accessibilityIdentifier("ekg-heartbeat")
        }
    }

    static func tone(_ mode: EkgHeartbeat.Mode) -> Color {
        switch mode {
        case .beating: return .green
        case .flat: return .secondary
        case .interrupted: return .orange
        }
    }

    @ViewBuilder
    private static func drawn(_ drawing: EkgHeartbeat.Drawing) -> some View {
        switch drawing {
        case let .trace(mode, beats):
            Group {
                if mode == .beating {
                    EkgTraceShape(beating: true)
                        .stroke(style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                        .keyframeAnimator(initialValue: EkgBeatFrame.rest, trigger: beats) { line, frame in
                            line.mask(alignment: .leading) {
                                GeometryReader { geo in
                                    Rectangle().frame(width: geo.size.width * frame.reveal)
                                }
                            }
                            .opacity(frame.opacity)
                        } keyframes: { _ in
                            KeyframeTrack(\.reveal) {
                                LinearKeyframe(0, duration: 0)
                                CubicKeyframe(1, duration: 0.54)
                            }
                            KeyframeTrack(\.opacity) {
                                LinearKeyframe(1, duration: 0)
                                LinearKeyframe(1, duration: 0.54)
                                CubicKeyframe(0.4, duration: 0.66)
                            }
                        }
                } else {
                    EkgTraceShape(beating: false)
                        .stroke(style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                }
            }
            .foregroundStyle(tone(mode))
            .frame(width: 34, height: 10)
        case let .still(mode, text):
            HStack(spacing: 4) {
                Circle().fill(tone(mode)).frame(width: 6, height: 6)
                if let text {
                    Text(text)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }
        }
    }
}

/// One beat's animated values: how much of the trace is drawn, and its ink.
struct EkgBeatFrame {
    var reveal: CGFloat
    var opacity: Double

    /// At rest, before any beat and after each one: the whole trace, faint.
    static let rest = EkgBeatFrame(reveal: 1, opacity: 0.4)
}

/// The web's two paths (`EkgHeartbeat.tsx`, viewBox 40×12), scaled to fit.
struct EkgTraceShape: Shape {
    let beating: Bool

    static let beatPoints: [CGPoint] = [
        CGPoint(x: 1, y: 6), CGPoint(x: 13, y: 6), CGPoint(x: 15, y: 4.5), CGPoint(x: 17, y: 6),
        CGPoint(x: 19, y: 1), CGPoint(x: 21.5, y: 11), CGPoint(x: 23.5, y: 6), CGPoint(x: 26, y: 4.8),
        CGPoint(x: 28, y: 6), CGPoint(x: 39, y: 6),
    ]
    static let flatPoints: [CGPoint] = [CGPoint(x: 1, y: 6), CGPoint(x: 39, y: 6)]

    func path(in rect: CGRect) -> Path {
        let sx = rect.width / 40, sy = rect.height / 12
        let points = (beating ? Self.beatPoints : Self.flatPoints)
            .map { CGPoint(x: rect.minX + $0.x * sx, y: rect.minY + $0.y * sy) }
        var path = Path()
        path.addLines(points)
        return path
    }
}
