# Groupings and containers: the primitives we build to

*Bain Luck — "Probability, not betting." Written by Fable from Alex's direction, Fri Nov 6, 2026, 1:50 PM PT. The model Alex endorsed in chat at 1:44 PM ("brilliant — document that in a way that we build to it and never lose it"). Canonical copy: `docs/design/grouping-primitives.md` in the repo; working copy on issue #12221. Read this before any grouping, container, Discover card, catalog or proposer work. Change it only by PR, with Alex's word on anything that changes a primitive.*

## Why this exists

Alex's goal, in his words (Oct 31, recreated Nov 6): groupings on Discover and Sports — "Rotten Tomatoes ladders for a few different movies opening up this weekend," "probabilities of a few different elections," "two or three different things that seemingly have nothing to do with each other but have similar probabilities of happening" — "created dynamically, not as a result of a specific brainstorm and then hard-coded"; and containers "for events like an awards show, a sports playoff, or an election, where a number of events might be related," and "other kinds of containers that we may want to dynamically create." He does not want to be "the human in the loop watching like a hawk to see if new formats SHOULD be possible," and he does not want to "manually spin up a page when the Oscars or March Madness are coming around."

Today (Nov 6) every grouping and container we serve is a hand-built *kind* whose *instances* come from live data: a person chose each of the 16 definitions in `backend/data/containers/`, and each kind's module wires its files in by name (part-1 brief on #12221). That is the gap this model closes: the same machinery, with the choosing done by a program and checked by people.

**The model in one line: one machine, two outputs.** A Discover grouping card and a container are the same thing rendered at two sizes. The card is the small rendering of a set; the container is the big one; the card opens into the container.

## The five primitives

### 1. Atoms

An atom is a market, prop or future as a venue sells it, with two things we already compute:

- its **shape** — one of the six shapes in `backend/app/utils/market_shape.py` / `frontend/lib/marketShape.ts` (binary; one-winner field; ladder/threshold; range; head-to-head; and the quantity group) — the contract every surface keys off (standing rule, Aug 2026);
- its **frame** — the content-understanding frame (#1809): subject, measure, comparator, value, unit, horizon/deadline; plus venue, settlement state and the twin it belongs to, if any.

Atoms are finite by construction. Venues sell a bounded number of shapes, and a new venue product shows up as a new shape, a new measure or a new series — all three are detectable (see *Keeping the map current*).

### 2. Relations

A relation is a fact between two or more atoms. The vocabulary is small and finite:

| Relation | Meaning | Where it already lives |
|---|---|---|
| same subject | the same team, person, film, race, city | the frame's subject; entity registers |
| same measure | the same thing being measured (win, RT score, snowfall, rate) | the frame's measure and unit |
| same window | the same deadline, day, week or season | the frame's horizon; `same_deadline_board.py` |
| same event / series | one game, one playoff series, one awards show, one election | event identity; NFL week assembly (#5341); series context (#9715) |
| twin | the same proposition on two venues | the explicit twin register (#11885, #11890) |
| sibling | atoms that differ in exactly one slot | the Oct 7 sibling rule; sibling families |
| yardstick | unrelated subjects with similar probability | `yardstick_pair.py` |
| movement | a change over a window | the movement pool; `update_max_movement` |
| implies / path / by-when | one proposition entails or precedes another | the near-twin rulings (Nov 4) |

A relation is computed from atoms and their frames; it is never typed in by hand except the twin register, which is a hand-kept list by ruling.

### 3. Sets

A set is a **selector** over atoms using relations — never a hand-picked list of market ids. Examples, in Alex's own cases:

- "every Rotten Tomatoes ladder whose film opens within 14 days" — same measure + a window;
- "the Red Sox' next three games" — same subject + time order, within a window;
- "pairs across different domains within two points of each other" — the yardstick relation;
- "everything attached to NFL week 10" — same event, by schedule;
- "every category of the 2027 Oscars" — same event, many fields;
- "every race for this office in this election" — same event, same measure;
- "this playoff series: its games, the series future, tonight's home-run props" — same series across three shapes.

A **kind** is a selector with its parameters left open (`same_deadline_board`, `sibling_family`, `yardstick_pair`, `field_leaders`, …). A **definition** is a kind with its parameters filled in (today: one file per card in `backend/data/containers/`). Today a person fills in every definition. Under decision 60-A (Alex, Nov 6), definitions are files in a folder loaded by kind, so adding a file makes a new card and container with no code change; under the proposer (part 1 of #12221), a program fills in definitions and people grade them.

Invariant: **a set is reproducible from its selector.** Given the same atoms and the same definition, two runs produce the same members, in the same order, with the same reasons. A definition that cannot explain why a member is in or out is not a definition.

### 4. Presentations

A set is rendered at one of two sizes:

- **A grouping card** — the small rendering, for Discover, Sports, search and the category pages: a ladder (field or threshold comparison), two rows (Congress control, the yardstick pair), a strip (the next three games), a matrix (the awards picture), a bracket (a playoff), a mover (change over a window). Card forms are a finite catalog too (#11940), and each reads the set's numbers through the shared probability formatter — whole numbers, the combined probability when there is one, a single source with attribution when there is not, never a number for a settled or unpriced row.
- **A container** — the big rendering: a page whose sections are each a set with its own card form, plus the things a page can carry that a card cannot (history, the canonical event cards for each member, a "related" section, captions). Containers feel like cards (ruling 31-A): no permanent navigation to them, reachable from the card that opened them and from search.

The rule that ties the two: **one definition yields both renderings.** The card is the container's summary; tapping the card opens the container; a container can be "the one the card opened" rather than the canonical page for its topic (Alex, Oct 7 and Nov 5).

Captions and commentary are a presentation step. An LLM may write them under the evals rule: it never writes a number; every figure on the page is read from the set, labelled with when it is true and linked to its source.

### 5. Triggers

A trigger is what makes a set exist without a person:

- **calendar** — a week starts; nominations are announced; a series starts tonight; a film opens Friday;
- **market availability** — a venue lists a new series (the 2027 Oscars categories; March Madness regions), so a container becomes possible;
- **movement** — things stack up: two unrelated atoms land within a point of each other; a field's leader changes; a big swing;
- **settlement** — results arrive; a recap set replaces the live one; settled means settled.

A trigger plus a kind is a **proposer**. The loop, from part 1 of #12221: *the model proposes, the existing rules verify, people grade.* A proposal is verified by the kind's own truth checks (the same ones hand-built definitions pass today), graded on cards set aside from tuning, and a kind earns a **licence** before any of its proposals reach a reader; one wrong card served suspends the kind. No model is called during a page load; proposers run on the worker, on a schedule, with the price printed before each run and a cap (decision 61).

## Alex's examples, mapped

| Alex's example | Atoms and relation | Trigger | Card | Container |
|---|---|---|---|---|
| RT scores for films opening this weekend | ladders; same measure, release window | calendar (release dates) | ladder comparison | "Opening this weekend" |
| the next three Red Sox games | head-to-head; same subject, time order | calendar (schedule) | three-game strip | the series or week hub |
| snow tonight vs a home run tonight | binaries; yardstick | movement (similar probability) | two rows | the pair (tiny, optional) |
| an NFL week | games, props, futures; same event | calendar (week starts) | week round-up | the week hub (#5341, automatic since Nov 4) |
| an awards show | fields; same event, many categories | market availability + calendar (nominations) | field-leader cards | Awards Season (#11935) |
| an election | fields and binaries; same event, same measure | calendar | Congress two-row card (ruling) | Midterms (live) |
| an MLB playoff series | games + series future + HR props; same series | calendar (series starts) | "who homers tonight" field card | the series hub |

## Keeping the map current without a hawk

The finite list is **shapes × relations × card forms**, not topics. New venue products appear as a new shape, a new measure, or a new series. A **sentinel** (standing rule: sentinels, not Alex's eyeball) watches three counts on the worker and files an issue when a threshold trips:

1. atoms whose shape or frame fits no known kind (the frame already reports an unclassified count);
2. new measures or units seen this week that no selector names;
3. new venue series (a category of markets with a shared prefix or event) that no container definition covers.

Each finding is an issue with the atoms attached, routed to the containers/data lane. That is how "should a new format be possible?" gets asked by a program and answered by a person — once, in a PR, not by watching.

## What this model keeps from existing rulings

- The blend is the product; a card shows the combined probability when one exists and one source with attribution when it does not; partial coverage is a matching problem, never a card state (Oct 7).
- Settled means settled; a settled member renders its result, never a number.
- Errors never masquerade as empty data; a set that cannot be computed is absent and logged, never served empty.
- Containers feel like cards; no permanent navigation; findable in search (31-A). Novelty seats for new containers in Discover's opening (32). "Everything is eligible to be a Discover card"; ranking decides what shows (Nov 5).
- The catalog rulings (#11905 A–D, #11940 A–E) stand; this model says how the catalog's kinds get their definitions, not which kinds exist.
- No model calls during page loads; the proposer's spend is printed and capped (61).

## How to add a kind, and how to know this document is stale

To add a kind: write its selector (which relations, which parameters), its card form, its container sections, its truth checks, and the test that proves a set is reproducible; register it in the folder; propose definitions through the proposer or by hand; earn the licence; serve. If adding a kind required a step not listed here, this document is stale — open a PR against it, not a workaround.

## Open decisions as of Nov 6

59 (the Nov 10 week-one type), 60 (definitions live in a folder — Alex: A), 61 (proposer spend) — on NOW #11852. Parts 2 (containers) and 3 (the primitives validated against code, the enumerated map, the sentinel, staging) are briefs on #12221; part 3 may propose corrections to this document, which Alex rules on.


