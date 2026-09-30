# #9524 CI fixture corrections — SOURCE PASS

Independent source-only review of exactly two test-file changes on base 853ac35cc2d980bf60f3b6a3b238980bf9e8c18d. Exact SHA256 values are in the adjacent JSON.

- Seeded spread expectation adds contributor_outcome_ids=[302]. The fixture directly seeds outcome302 on market202, named Celtics -4.5, probability0.54 (test_route_events_seeded.py:279). The whole-dictionary assertion stays exact; probability, source, threshold, unknown observation, ungraded verdict and market identity remain unchanged. Period-market assertions are untouched.
- The BTTS reader scan explicitly distinguishes only stream_market_ids and closed_winner_market_ids from rendered row lists and checks their elements are positive integers. All other list buckets still traverse every row and forbid BTTS in market_name. Known-good moneyline, exact readable BTTS heading, Yes meaning, probability, both-venue grouping, and non-merging assertions remain intact.

No business assertion was removed or weakened, and no production code changed. No tests or gates were rerun by the reviewer; author owns the focused execution and CI result.
