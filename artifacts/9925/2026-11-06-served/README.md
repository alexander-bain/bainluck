# #9925 served web proof — November 6, 2026

Pillars: DISCOVER / MATCHING / TRUTH. Ship: AI and Oscars theme cards open their automatically maintained collection pages; the page membership governs the card (decision 62-A).

PR #12228 merged as `e312e322a5f7f1d9aa3ed257eb5ab117641f5d6d` after green CI, exact-head `claude[bot]` approval and Fable ACCEPT at `f47e0d809eb782877b19b8c0741dbe35f28ca586`. Master run 42315386102 deployed successfully at 6:01 PM PST. Public `/health` then returned `e312e322`.

Actual public UI, 390 × 844, 6:05–6:10 PM PST: Discover AI card → AI collection → OpenAI/Anthropic IPO market → browser Back restored AI at scroll 0. Discover Oscars card → Oscars 2027 collection → Best Picture market → browser Back restored the collection at scroll 506.5; Back to Discover restored scroll 1544 and the collection entry at viewport top 403.25. Screenshots are genuine browser JPEG captures converted to PNG with sips, with no visual editing.

Public API pagination read all 566 shown AI members at revision 131 (six pages) and 419 Oscars members at revision 60 (five pages). Every displayed member of AI (four), Oscars (five), and IPOs (three, also linking AI) was directly shown on its destination page. No folded alias inference was needed. Counts remain independent of the feed preview. `membership-proof.json` records the identifiers.

The source change reuses the existing rule selector, hourly assembly, publication and revision snapshots. It introduces no manual members and no production data write. A frozen inventory is not a claim that membership changed during these minutes; automatic maintenance is the reused existing path, covered by the lifecycle gates recorded on the PR.

Released singles remain immediately after their theme at the attachment stage, before later seating; they are not claimed to be globally reranked. The public response includes the AI outsiders immediately after AI and the Grammy outsider immediately after Oscars; see `feed-placement-proof.json` for actual seats and scores. A browser deck from the predeploy session reappeared once during navigation without collection links. Reload fetched the projected deck, and the later complete return journey retained its collection links. This proof covers the fresh served web deck; it does not assert every already-open client was invalidated at deploy.

This completes the bounded November 6 web goal. #9925's older cross-domain and installed-native acceptance remains separate; these captures do not close the entire historical issue.

- [AI collection](https://bainluck.com/collections/ai)
- [Oscars collection](https://bainluck.com/collections/oscars-2027)
