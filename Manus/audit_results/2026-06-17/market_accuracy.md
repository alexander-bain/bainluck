Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to select 4 events, then audit each for monotonicity, cross-game contamination, and cross-reference with Kalshi.

The event page for this completed NBA Finals game only shows Win Probability and Score Differential charts. It doesn't appear to have "Projected Scoring" or "Period Markets" sections visible. Let me check if a game that's scheduled (not completed) has those sections, or try a different approach.

The Market Accuracy Ground Truth audit is complete. I've produced a comprehensive JSON report and a readable markdown summary. Here are the key findings:

**Monotonicity Violations: 2**
1. **CRITICAL** — MLB Dodgers vs Rays player props show two different markets merged into one display (team runs + game total), causing a 13% → 80% probability jump
2. **WARNING** — NHL series total goals thresholds displayed out of order (50+ goals at 50% shown before 45+ goals at 38%)

**Cross-Game Contamination: None detected** across all 4 events (2 NBA Finals, 1 NHL Stanley Cup Finals, 1 MLB regular season)

**Kalshi Cross-Reference:** BainLuck correctly shows Kalshi's 9 thresholds for NBA Game 6 1H total, plus 9 additional from Polymarket (different source, not different game)

The attached files contain the full structured JSON output and a detailed markdown report.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/MTPMvo6ikjicz9tcFdeYF6/sandbox/yV9RZ2NWZNctWlYhMQOovr_1781716693185_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvTVRQTXZvNmlramljejl0Y0ZkZVlGNi9zYW5kYm94L3lWOVJaMk5XWk5jdFdsWWhNUU9vdnJfMTc4MTcxNjY5MzE4NV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE3OTg3NjE2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=qH6UyXQhxGTX39ZikC0UskJa2rAUEYi5ERt-BhzVsTzHJpJjwDQHw1tCXNwyaaGpBEHHpQkfBMnaGLYOK4u6PTYHHS0a3ehjWFpxRrPdgzT19Thob-DuSbxXy1ouDGR4PbRc9jiJV1xDNvNB3NSxi1Cb948fkUm0qGS7EH06FYZUo6svzz~awq~nWCatgiyd3NKAa1GR6KMDXulTFOA4wsaTVVWzFHfyL7ytmqxWY1ZYRk1dSmzy390HHxI-XqP0U3rCVFep5ho094~MHzk243~2my5gVXODpg8vpZ8J3o67rK9ChfOylYJvr1tTtfGtqahMPVAWPTFRfulBSoeWPQ__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/MTPMvo6ikjicz9tcFdeYF6/sandbox/yV9RZ2NWZNctWlYhMQOovr_1781716693185_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdF9yZXBvcnQ.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvTVRQTXZvNmlramljejl0Y0ZkZVlGNi9zYW5kYm94L3lWOVJaMk5XWk5jdFdsWWhNUU9vdnJfMTc4MTcxNjY5MzE4NV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRGOXlaWEJ2Y25RLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Q3C3H8H36Pn-bZDbHciyB5MzxgAFYEsIip1Hf-kBMJMYHeoliZ69CntFt-vmwjpBwNVmkPJiuhgWavkSAAjXH3v4lXOInK0SXpOSbH~bjccoZfe1Rzu5GBCyElpnzScrOGW2VqPmGuhrKvTTMq9InCKNE-QGQHEEJMX4WrvYZ1pK3d3leNkeA57vy~qJUjTI13ivSBTOdViXiWPp40OhA8C~C-06D1e~F~7dQVGRlCXm7Jr~OJ7Mcyw~Tyw4gK8~-V6hptwNBmSqyD83fWmHuE~OG7vTnr7wiskJYAs6WElDcuPZjCU7so6~kN9jlQcSOPMXcpVNDDE9rHwNbqzuzA__