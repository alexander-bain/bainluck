Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to select 4 events, then audit each for monotonicity, cross-game contamination, and cross-reference with Kalshi.

I notice that this completed MLB game event page doesn't have "Projected Scoring" or "Spread" sections - it only shows Win Probability, Additional Markets (player props), and Bigger Picture. Let me search for events that have the projected scoring sections - these are likely on upcoming/scheduled games. Let me look for upcoming NBA Finals games or other scheduled events.

I have completed the Market Accuracy Ground Truth audit for bainluck.com event detail pages.

### Key Findings
1. **Section Availability:** The sections mentioned in the instructions ("Projected Scoring", "Projected Combined Scoring", "Spread" with grouped outcomes, and "Period Markets") do **not** exist under those exact names on most event pages. For scheduled MLB games, these sections are completely absent.
2. **NBA Finals Structure:** On NBA Finals game pages, the equivalent data is found under "Total maps" (Full game and 1st half), "Margin maps", and "Player Props".
3. **Monotonicity Check:** I verified the monotonicity for all Full Game Over/Under thresholds, 1st Half Total thresholds, and Player Prop thresholds across three NBA Finals games (Games 1, 2, and 3 between the Knicks and Spurs). All thresholds passed the monotonicity check (probabilities were strictly decreasing or non-increasing).
4. **Cross-Game Contamination:** I compared the thresholds across Games 1, 2, and 3. While Games 1 and 3 shared identical thresholds and Game 2 had slightly different ones (offset by 1 point), this aligns with standard market behavior based on pre-game projected totals and does not indicate contamination. No outcomes from previous games were found on subsequent game pages.
5. **Kalshi Cross-Reference:** The NBA Finals have already concluded (Knicks won), and Kalshi has removed all game-specific markets (1H Total, Spreads, Player Props). Only 2027 futures remain on Kalshi, making a live cross-reference impossible for these completed events.

The detailed structured data has been compiled into the attached JSON report.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/TFsTVRkna8JQFK4eHwa6GH/sandbox/SL3HSuUzJatmRfelxrrHqF_1783094579398_na1fn_L2hvbWUvdWJ1bnR1L2F1ZGl0X3JlcG9ydA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvVEZzVFZSa25hOEpRRks0ZUh3YTZHSC9zYW5kYm94L1NMM0hTdVV6SmF0bVJmZWx4cnJIcUZfMTc4MzA5NDU3OTM5OF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJGMVpHbDBYM0psY0c5eWRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE4MzAyOTc2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Ub~PkSbfxqTd2chKwEOpmdUNLlCNr1CieTDoe9Ypu81MaLESL-JdUMQzZ7rkRBvCONr-KKgAiHmyQWoS~dbw2y2oJW1wrUbM0YrWjy8eyzFKBFPomDeu8NgFhgIX~7fEMuggCWOdMY-VIc2GLMB7FN1MghyCFOPrSVoeTwzOHOb~EEdjvhVzigRTh1xyRy709C90IfIIRy96CBbWuzIwvA-NnG2aw3PzReZEKid6vNUsO0R5CgrynMJZBO1djCyW9weibu1WkzCSuLpmLvrw8N56HIs841WM-2ou9Upju9HfgrjP54MSTa~pACreW9I8zq9MMZ2v3zfbJrX8fB7vuQ__