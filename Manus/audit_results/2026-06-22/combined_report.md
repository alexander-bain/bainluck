# Manus Health Audit — 2026-06-22

**Modules run:** 3
**Completed:** 2
**Failed/Timeout:** 1
- feed: timeout

---

## Event Detail Deep Audit

Starting the Event Detail Deep Audit on bainluck.com. I'll browse the site, select 6 events across different sports and statuses, then perform a comprehensive quality audit of each event detail page.

Events selected. Now auditing each of the 6 event detail pages against the full checklist. Starting with the first live event (Rei Sakamoto vs Anton Matusevich, Wimbledon Tennis).

Audit checklist completed for all 6 events. Now capturing desktop and mobile screenshots for each event page.

The Event Detail Deep Audit is complete. 

I've audited 6 events across 3 sports (Tennis, MLB, Soccer) covering LIVE, FINAL, and UPCOMING statuses. The health score came out to 19/100 due to several critical data mismatches and rendering issues.

Key critical findings include:
- Chart tooltips showing wildly different probabilities than the hero section for live events
- The Score Differential chart completely failing to render on completed soccer games
- Nonsensical probabilities appearing in the Related Futures section (e.g., heavy underdogs showing 49% to win by 4+ goals)
- Flatlining source data defaulting to 50% instead of hiding when unavailable

The full structured markdown report is attached, along with a ZIP file containing all desktop and mobile (375px) screenshots for the 6 audited events.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/HZrrJ6HEbMRLVYADLyFBQE/sandbox/wWKchsOrAgjbYHS5yG60hj_1782129910671_na1fn_L2hvbWUvdWJ1bnR1L1FBX0F1ZGl0X1JlcG9ydA.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvSFpycko2SEViTVJMVllBREx5RkJRRS9zYW5kYm94L3dXS2Noc09yQWdqYllIUzV5RzYwaGpfMTc4MjEyOTkxMDY3MV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDFGQlgwRjFaR2wwWDFKbGNHOXlkQS5tZCIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=HJ5vwXbWnAlwjdG~nNF7yTg3G72VAF2XX4sc7pFoBHlLk84gzncDsYM6IpDEDbxlprlhZea3LQohj99GVxPbc3tzy8u4uDJY9VUucKQ~KZ7pqAHTosHYPfgvzS5VWbGv1hjmzRHjrP4Xm~BYwVnvoP3VnVoVseKxdF0XPV4wwoSfKybU2BsApgzqguRo3Eotw04LHoACRdP6OIjpR9Tra0GVvyOmIqr9Otcd~61DbwBH2LesWSa6kyF35z-WVtwXq6bszWNKEK5Xlt9zt6wXyM27OjIkp5BJPIJTF8vDr2~u4dcp449ISjSH3jSl8qucmyD1e8M33XqCOMXI4K0EvA__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/HZrrJ6HEbMRLVYADLyFBQE/sandbox/wWKchsOrAgjbYHS5yG60hj_1782129910671_na1fn_L2hvbWUvdWJ1bnR1L2F1ZGl0X3NjcmVlbnNob3Rz.zip?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvSFpycko2SEViTVJMVllBREx5RkJRRS9zYW5kYm94L3dXS2Noc09yQWdqYllIUzV5RzYwaGpfMTc4MjEyOTkxMDY3MV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJGMVpHbDBYM05qY21WbGJuTm9iM1J6LnppcCIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=sIunFGDttc4eoJ0a9aavwuOLK0KdaK8HlceDslWK7ecDDTAlTE0SplfYaF9IjDNfWkCF7-OQ~HWTFqd1z9nDRV54XiHVOxZEZv5faykYw~HLc49N7zIFwN7ad5AFHyqiMyszEULSTLbxYlPzGLEQ06vDE6O52p6Vrru3yj6OjBzcrbdn1p1nRO4Fu7ImxSQbiKLJ7S3LjB3N4gpIKhvOAsKiFiVAq9uJ0kTnojeDxJryvOd7Q~wVjEAuIQ7soR1Z8StVZy1mApq7mBrDpLk2xnMJKa~DAY~BzyRxcq3D5a5pf4kmTbc8ho4kfvBldkPLyn-~hOAxdBukjpU63kJNAg__

---

## Championship Grid Deep Audit

Starting the Championship Grid Deep Audit for bainluck.com. I'll systematically audit each playoff grid (NBA, NHL, MLB, Golf) checking structure, team identity, probability quality, source verification, interactivity, and mobile rendering.

Now performing source verification - checking MLB team odds against live Kalshi and Polymarket data for 5 teams (Dodgers, Yankees, Braves, Brewers, Phillies).

I have completed the deep audit of the championship grids on bainluck.com. The comprehensive audit report is attached.

The MLB grid is functioning excellently and matches live Kalshi/Polymarket data within acceptable margins. However, critical issues were found on the NBA, NHL, and Golf grids regarding missing teams, missing columns, and incorrect data formats. Mobile rendering was also tested and found to be acceptable with horizontally scrollable tables.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/hj8iSu6WrJnBg9MUcZbwDS/sandbox/9vnuVxdOyZfvp3GrpMUVY0_1782129731401_na1fn_L2hvbWUvdWJ1bnR1L2NoYW1waW9uc2hpcF9ncmlkX2F1ZGl0X3JlcG9ydA.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvaGo4aVN1NldySm5CZzlNVWNaYndEUy9zYW5kYm94Lzl2bnVWeGRPeVpmdnAzR3JwTVVWWTBfMTc4MjEyOTczMTQwMV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJOb1lXMXdhVzl1YzJocGNGOW5jbWxrWDJGMVpHbDBYM0psY0c5eWRBLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=XRZONeLVrOfji5uIUIFkr9uDSPGeLN0ow9Hmc6dB9GOH1LNminplRip7QX3b4SIyW75M-BJcApo1RxuClsnN2cLyLV5I4JA1MdD~-RUBxCsvE5KZTC~A4x16lwGza0PWCBPR3x4NBY2qlS-C74LlFNv8MefM0BtjUWrB4yZWDlTyTsUEc3T6bkOzjvO4h87G2n~QSzsiPhjX3DSd6wISImBYxolSyOlnHJSvLap78DQT2sMwlq62TbEutC2Mxr2fMppPgQIoRgMqegogpeVMRsjvJ5k9Ctgustb~xk~fiLvEfUYeLYqD45V3ORBp913QBz4lTuH5f3-OJRay7SLwxQ__
