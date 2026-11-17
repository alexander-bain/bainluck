# NFL roundup source-mark contract preview

These 390 pt SwiftUI renders use the complete existing historical November 2 fixture: all 16 registered source markets, every outcome, and the normal register/compositor. They are local previews of the proposed server payload. They are not current production numbers or installed-app captures. Builder C owns installed presentation acceptance.

- `roundup-source-marks-fixture-390.png` shows all four summary rows before/after and the source sheet for the rounded NFC South tie. The unchanged row number belongs to Buccaneers; the method says whose inputs it explains.
- `roundup-container-marks-fixture-390.png` shows all four outcomes for each of the four selected member cards.
- `complete-input-fixture.json` is the full input; `before-payload.json` and `after-payload.json` are both complete outputs. Removing only `source_mark` preserves every old field. Their combined compact JSON sizes are 7,961 and 19,527 bytes, respectively; these are fixture sizes, not production latency measurements.
- Source times remain absent. The register's legacy age is a row-touch time and cannot establish when either input price was read.

A public container response and all 16 public market details were saved on November 17. Detail normalizes some fields before returning them, and its supported representations do not expose the raw pair used by this roundup. Those responses were not substituted for the raw inputs or reverse-engineered from odds.

The SwiftUI harness uses the existing source button/sheet contract and whole-percent formatter. It demonstrates the payload, not final app layout or navigation. No outcome was removed for rendering.
