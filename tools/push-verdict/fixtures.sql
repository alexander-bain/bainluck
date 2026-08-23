-- Synthetic rows that drive EVERY branch of the verdict ladder.
--
-- One `scenario` per expected verdict. The self-test groups by it and asserts
-- the CASE returns the expected string for each — which is the only way to know
-- the ladder can say anything other than the one answer production happens to
-- give today. UX-P119 shipped three proofs whose checks silently never fired
-- (#2065's monoculture check below n=4, #2084's wrong payload path) — a verdict
-- that has only ever produced one value is indistinguishable from a constant.
--
-- Column order and names must match what the CASE reads: platform, token_kind,
-- is_active, device_token, created_at.
(VALUES
  -- 1. Today's real production shape: two macOS rows, no ios row anywhere.
  ('1_broken',     'macos', 'apns', true,  'f1e2eb09aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', TIMESTAMPTZ '2026-05-21 01:34:28+00'),
  ('1_broken',     'macos', 'apns', true,  '5d64e37abbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', TIMESTAMPTZ '2026-06-03 22:36:40+00'),

  -- 2. An ios row exists, but it predates the floor: a PREVIOUS session's row
  --    must never be able to certify THIS session. Without the floor clause
  --    this scenario reads as FIXED forever after the first success.
  ('2_stale',      'macos', 'apns', true,  'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', TIMESTAMPTZ '2026-05-21 01:34:28+00'),
  ('2_stale',      'ios',   'apns', true,  'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', TIMESTAMPTZ '2026-08-01 10:00:00+00'),
  ('2_stale',      'ios',   'fcm',  true,  'eeeeeeee:APA91bHstale-looking-firebase-registration-token-value', TIMESTAMPTZ '2026-08-01 10:00:00+00'),

  -- 3. The failure #1159's own comment predicts: a row LABELLED fcm that holds
  --    a raw 64-char APNS hex token. messaging.send() rejects it, so the digest
  --    still has no audience — but a naive "is there an fcm row" check says yes.
  ('3_mislabeled', 'ios',   'apns', true,  '1111111111111111111111111111111111111111111111111111111111111111', TIMESTAMPTZ '2026-08-23 18:00:00+00'),
  ('3_mislabeled', 'ios',   'fcm',  true,  '2222222222222222222222222222222222222222222222222222222222222222', TIMESTAMPTZ '2026-08-23 18:00:00+00'),

  -- 4. The outcome we want: both kinds, both active, both after the floor.
  ('4_fixed',      'ios',   'apns', true,  '3333333333333333333333333333333333333333333333333333333333333333', TIMESTAMPTZ '2026-08-23 18:00:00+00'),
  ('4_fixed',      'ios',   'fcm',  true,  'fMEP0vJq:APA91bH-real-shaped-firebase-registration-token-abc123', TIMESTAMPTZ '2026-08-23 18:00:00+00'),

  -- 5. APNS reached the backend, Firebase did not. This is the outcome #2109
  --    considers most likely if the entitlement is fine but messaging init is
  --    not, and it is NOT a pass: the Morning Digest still cannot deliver.
  ('5_partial_apns', 'ios', 'apns', true,  '4444444444444444444444444444444444444444444444444444444444444444', TIMESTAMPTZ '2026-08-23 18:00:00+00'),

  -- 6. fcm with no apns twin. Should not happen (the FCM token is minted FROM
  --    the APNS one), so it must fall to the ELSE and say "inspect", never
  --    silently to FIXED.
  ('6_partial_fcm',  'ios', 'fcm',  true,  'gNQR1wKr:APA91bH-orphan-firebase-token-with-no-apns-sibling-xyz', TIMESTAMPTZ '2026-08-23 18:00:00+00')
) AS t(scenario, platform, token_kind, is_active, device_token, created_at)
