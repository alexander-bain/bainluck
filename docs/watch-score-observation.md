# Foreground selected-game score age

PILLARS: TRUTH · FORMATTING.
SHIP: The selected game's foreground Live Activity can show the age of its score
when the server supplies a producer observation, instead of always reporting an
unknown score age.

This candidate rides the reviewed foreground ActivityKit source at `7e30a2e`.
It decodes optional `score_source` and `score_observed_at` in `EventDetail`, then
passes the score producer clock through the existing phone snapshot adapter only
for a complete nonnegative score tuple with nonempty source attribution. These
scores and observation fields are immutable values from one served response, so
price-only stream updates cannot detach the score from its clock.

The backend detail route calls `_format_event`, which emits the displayed scores
and merges `score_observation_fields(event)`. That helper serves the observation
and source together. The backend projection's real-formatter test verifies this
authority chain; this change adopts the existing additive response fields.

Missing/invalid dates, missing attribution and partial/invalid scores retain
unknown age. Price timestamps, row updates and phone receipt time are never score
authority. No clocks are created, no score winner is inferred, and no activity
token or background transport behavior is introduced.

Three XCTest cases cover real snake-case decoding, zero-score age independent of
price, orphan/invalid readings and backwards-compatible omitted fields. Hosted
full `BainLuckTests` must execute these tests before native source acceptance.
No local Xcode, simulator, installation or device acceptance is claimed.
