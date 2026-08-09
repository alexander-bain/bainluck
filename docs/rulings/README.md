# docs/rulings/ — one file per ruling

**"Append a ruling to PRODUCT-BRAIN" now means: add a new file here, and one index line there.**

Ruling 001 is the ruling that created this directory; read it for the WHY.

## The mechanics

1. Pick the next free number: `ls docs/rulings/ | tail -1`. Three digits, zero-padded.
2. Create `docs/rulings/NNN-<slug>.md`. Slug is lowercase, digits and hyphens only.
3. The file starts with exactly this shape — the integrity test parses it:

   ```markdown
   # RULING 042 — Short imperative title

   date: 2026-08-09
   author: Alex
   issues: #1234

   <the ruling, and the WHY behind it>
   ```

   `date:` and `author:` are required. `issues:` and `supersedes:` are optional.
4. Add ONE index line to `docs/PRODUCT-BRAIN.md`, in the `## RULINGS INDEX` section,
   in ascending number order:

   ```markdown
   - [042](rulings/042-short-slug.md) — 2026-08-09 — Short imperative title (Alex)
   ```

5. Run `python3 -m pytest tests/test_product_brain_integrity.py` from `backend/`. It fails if a
   file has no index line, an index line has no file, a number repeats, the index is out of
   order, or the heading number disagrees with the filename.

## Two collisions, and what to do about each

**Same number, two lanes.** Both lanes read `041` as the max and both write `042`. The integrity
test catches it. **The later-merged lane renumbers ITS OWN file upward** — never the other one.
Renaming a brand-new file costs nothing: no reader has cited it and no patch-id matters, because
the file did not exist upstream either way.

**The index line itself can still conflict.** Two lanes appending adjacent lines to the same
section is a genuine git conflict, and this directory does not remove it — it makes it *cheap*.
Resolve by **keeping both lines and sorting by number**. That is mechanical: there is no prose to
re-read, no judgment about which wording survives, and nothing can be silently dropped because
the test fails if a file loses its line. What this directory removes is the expensive half — an
80-line block of ratified prose being merged by hand.

## Why the old sections are still in PRODUCT-BRAIN

Everything ruled before 001 stays exactly where it is. Migrating it would have rewritten the file
this whole system exists to protect, and the CI markers pin those sections by substring. The
in-file history is the archive; this directory is where new rulings go.
