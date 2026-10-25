#!/usr/bin/env bash
# Source-only reader checks. No Xcode build, simulator, app or device.
# Uses the exact XCTest methods with an assertion shim and minimal model
# surfaces. Native must separately run these tests against the real app.
set -euo pipefail
root="$(cd "$(dirname "$0")/../../.." && pwd)"
out="$(mktemp -d "${TMPDIR:-/tmp}/folded-preview-reader.XXXXXX")"
trap 'rm -rf "$out"' EXIT
{ echo 'import Foundation'; sed -n '/^nonisolated struct LiveBlendPoint:/,/^}/p' \
  "$root/ios/Bain Luck/Bain Luck/Utilities/LiveChartEdge.swift"; } > "$out/LiveBlendPoint.swift"
if [[ "${1:-}" == "--baseline" ]]; then
  git -C "$root" show "${2:?baseline commit required}:ios/Bain Luck/Bain Luck/Utilities/BlendPreview.swift" > "$out/BlendPreview.swift"
  { echo 'import Foundation'; git -C "$root" show "${2}:ios/Bain Luck/Bain Luck/Utilities/LiveChartEdge.swift" | sed -n '/^nonisolated struct LiveBlendPoint:/,/^}/p'; } > "$out/LiveBlendPoint.swift"
  swiftc -swift-version 5 -default-isolation MainActor -D STANDALONE_PREVIEW_READER -parse-as-library "$out/LiveBlendPoint.swift" "$root/tools/tests/native-folded-preview/ReaderSupport.swift" \
    "$root/ios/Bain Luck/Bain Luck/Utilities/FoldRevision.swift" "$out/BlendPreview.swift" \
    "$root/tools/tests/native-folded-preview/RegressionProbe.swift" -o "$out/regression-probe"
  "$out/regression-probe"
  exit
fi
# Extract the unchanged value declaration and exact pure chart transforms;
# no SwiftUI view, model lifecycle or renderer is substituted or exercised.
python3 - "$root" "$out/ChartTransform.swift" <<'PYCHART'
from pathlib import Path
import sys
source = (Path(sys.argv[1]) / 'ios/Bain Luck/Bain Luck/Components/OddsChartView.swift').read_text()
start = source.index('struct ChartDataPoint:')
end = source.index('\n}', start) + 2
parts = ['import Foundation', source[start:end], 'enum OddsChartView {']
for name in ['extendingBlendToLiveEdge', 'extendingServedSourceSeries', 'heldReadingsBetween', 'inserting']:
    start = source.index('    static func ' + name + '(')
    end = source.index('\n    }', start) + 6
    parts.append(source[start:end])
parts.append('}')
Path(sys.argv[2]).write_text('\n'.join(parts))
PYCHART
sed -e 's/^import XCTest$/import Foundation/' -e '/^@testable import Bain_Luck$/d' \
  "$root/ios/Bain Luck/BainLuckTests/FoldedBlendPreview10090Tests.swift" > "$out/ReaderTests.swift"
swiftc -swift-version 5 -default-isolation MainActor -D STANDALONE_PREVIEW_READER -parse-as-library "$out/LiveBlendPoint.swift" \
  "$root/tools/tests/native-folded-preview/ReaderSupport.swift" \
  "$root/tools/tests/native-folded-preview/Assertions.swift" \
  "$root/ios/Bain Luck/Bain Luck/Utilities/FoldRevision.swift" \
  "$root/ios/Bain Luck/Bain Luck/Utilities/BlendPreview.swift" \
  "$out/ChartTransform.swift" "$out/ReaderTests.swift" "$root/tools/tests/native-folded-preview/main.swift" -o "$out/reader-checks"
"$out/reader-checks"
swiftc -swift-version 5 -default-isolation MainActor -D STANDALONE_PREVIEW_READER -parse-as-library "$out/LiveBlendPoint.swift" "$root/tools/tests/native-folded-preview/ReaderSupport.swift" \
  "$root/ios/Bain Luck/Bain Luck/Utilities/FoldRevision.swift" \
  "$root/ios/Bain Luck/Bain Luck/Utilities/BlendPreview.swift" \
  "$root/tools/tests/native-folded-preview/RegressionProbe.swift" -o "$out/regression-probe"
"$out/regression-probe"
