SELECT{{PREFIX_SELECT}}
  CASE
    WHEN COUNT(*) FILTER (WHERE platform = 'ios') = 0
      THEN 'BROKEN - zero ios rows exist at all, registration never reached the backend'
    WHEN COUNT(*) FILTER (WHERE platform = 'ios' AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') = 0
      THEN 'STALE - ios rows exist but none since the floor, this session produced nothing'
    WHEN COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'fcm' AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00' AND device_token ~ '^[0-9a-f]{64}$') > 0
      THEN 'MISLABELED - an ios fcm row holds a 64-char APNS hex token, messaging.send() will reject it'
    WHEN COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'fcm' AND is_active AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') > 0
     AND COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'apns' AND is_active AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') > 0
      THEN 'FIXED - ios apns AND ios fcm both landed, the digest has a deliverable audience'
    WHEN COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'apns' AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') > 0
      THEN 'PARTIAL - ios apns landed, ios fcm did NOT. APNS reached the backend, the Firebase half is dead'
    ELSE 'PARTIAL - ios fcm landed with no apns twin, unexpected, inspect the rows'
  END                                                                          AS verdict,
  COUNT(*)                                                                     AS rows_total,
  COUNT(*) FILTER (WHERE platform = 'ios')                                     AS ios_all_time,
  COUNT(*) FILTER (WHERE platform = 'ios' AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') AS ios_since_floor,
  COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'apns' AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') AS ios_apns_new,
  COUNT(*) FILTER (WHERE platform = 'ios' AND token_kind = 'fcm'  AND created_at > TIMESTAMPTZ '2026-08-23 00:00:00+00') AS ios_fcm_new,
  COUNT(*) FILTER (WHERE platform = 'macos')                                   AS macos_control,
  MAX(created_at)                                                              AS newest_row
FROM {{SOURCE}}{{GROUP}}
