# #1529 reader fixture: a game-winner question is filed under Other

PILLAR: TRUTH
SHIP: Event pages show game-winner questions and player props in their correct sections.

This is a fenced Codex fixture packet for the original #1529 reader gate. It precedes the correction queue. The JSON preserves observed rendered labels separately from synthetic guard specifications. It is not a production API capture and invents no provider ticker, market ID, player membership, date authority or grading evidence.

Evidence retained by Shopper: `/Users/bain/bainluck-dev/shopper/artifacts/shopper/1529-reader-20261021/`, especially `x-allmarkets-Other.png`, `x-allmarkets-Game_lines.txt`, `x-allmarkets-Player_props.png`, `w08-after-refresh.png` and `x-browser-back.png`. Root independently inspected the Other and Player props images and the three catalog text captures. The completed page shows the sole Kalshi game-winner question under Other; ordinary props are in their proper section. The special matchup-named player-contract container was not established on this page and remains UNKNOWN.

Source boundary at the frozen release: `_classify_game_market` already recognizes full-game moneyline and preserves the player-outcome rescue. `_build_game_markets` can append surviving full-game winners to `other_markets` without their semantic class, after the rescue. `buildQuestionCatalog` assigns `data.other` to Other and has no moneyline input. Therefore the visible failure is not proof that the classifier itself returned Other. The live row's ticker and exact classifier result remain unobserved.

Consume the paired cases when writing real producer/consumer regression tests. The fix may choose an additive semantic field, a typed response bucket or another safe contract; this fixture does not prescribe a field name or implementation. Tests must demonstrate the observed failure before correction and protect player-container rescue, period/F5/segment scope, unknown handling, quote withholding and existing grade truth. Do not infer a winner from a title in the frontend or modify stored grades to repair a catalog family label.

The full current census and CORE thresholds remain separate Measurement-owned gates. These fixtures and any later source/CI success do not pay production, native, special-container reader acceptance or closure. No live request or data change belongs to this packet.
