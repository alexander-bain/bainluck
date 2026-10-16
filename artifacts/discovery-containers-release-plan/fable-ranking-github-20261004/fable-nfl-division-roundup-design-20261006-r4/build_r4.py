# Revision 4 of the round-up card reference. Patches the revision 3 page and companion file.
# It removes states Alex withdrew and records rulings made after revision 3. No card rule,
# measurement or image is changed. Inputs: r3_page.html, r3.md, roundup-card-fixture-r3.json
import json, re

page = open('r3_page.html').read()
md = open('r3.md').read()

def rep(text, old, new, count=1):
    assert text.count(old) == count, (text.count(old), old[:70])
    return text.replace(old, new)
def cut(text, a, b, new):
    i = text.index(a); j = text.index(b, i); return text[:i] + new + text[j:]

F8 = 'Bain Luck blend · the 4 closest of 8 divisions'
NEW_RULINGS = [
 ("A division that cannot be blended is a data problem, not a card state.", "It is fixed with better matching, not with design. The card is shown only when every open division has a verified blend from both venues. If any one fails, there is no card, and the failure is reported as a matching defect."),
 ("The container shows each division with the product's existing card.", "A division winner is a \"field\" question and the product already has a card for it. No new card is designed. It must show the same blended number as the round-up."),
 ("The tag's grey gets a product name.", "<code>--text-secondary-strong</code>, added as part of the card build."),
]

# ---------------- page
page = rep(page, 'Revision 3, 10:20pm PT', 'Revision 4, Wed Oct 7, 12:10am PT')
anchor = '<li><b>The footer wording is accepted for now.</b> It can change if it looks wrong in production.</li>'
page = rep(page, anchor, anchor + ''.join(f'<li><b>{a}</b> {b}</li>' for a, b in NEW_RULINGS))
page = rep(page, 'The coordinator recommends adding a name for it, <code>--text-secondary-strong</code>; that is not yet decided and nothing has been added.',
 'Alex ruled that it gets a product name, <code>--text-secondary-strong</code>, added as part of the card build.')

# the all-eight specimen, lifted unchanged from revision 3
m = re.search(r'<figure class="fig"><div class="sp sp-light" data-state="all8".*?</figure>', page, re.S); assert m
fig8 = m.group(0)
fig8 = rep(fig8, '<figcaption>All eight divisions qualify. Wording accepted by Alex for now.</figcaption>', '<figcaption>The only footer. Wording accepted by Alex for now.</figcaption>')
FOOT = f'''<h2>The footer line in the product</h2>
<p>There is one footer. The card appears only when all eight divisions have a verified blend, so "of 8" is always true when the card is on screen. It uses the footer style above, unchanged, on one line.</p>
<div class="duo">
{fig8}
</div>
<p>If any division cannot be blended, no card is shown and the feed is unchanged. Revision 3 drew a footer for "four to seven divisions" and a "three of eight" state; both are withdrawn by Alex's ruling. The three-row layout above stays, as a layout other round-ups will use.</p>
<p>The headline stays "NFL division front-runners".</p>
<p>Not yet ruled: what the card says late in the season, when a division has been clinched and fewer than eight are still open. That is a settled question, not a data problem.</p>

'''
page = cut(page, '<h2>The footer line in the product</h2>', '<h2>When a number is old</h2>', FOOT)
page = rep(page, '<p>The placements are Fable\'s proposal; the rule and wording are the product\'s.',
 '<p>The placements are Fable\'s proposal; the rule and wording are the product\'s. The coordinator confirmed on Oct 6 that the product\'s mark can sit in both places unchanged and that the all-old and some-old rule matches the product\'s existing behavior. Exact fit is checked on the built card.')
page = rep(page, 'named <code>r3_&lt;state&gt;_light_&lt;width&gt;.png</code>.', 'named <code>r3_&lt;state&gt;_light_&lt;width&gt;.png</code> (states <code>all8</code>, <code>old</code>, <code>mixed</code>).')
assert 'data-state="partial"' not in page and 'data-state="three3"' not in page and '6 covered' not in page
open('roundup-card-reference.html', 'w').write(page)
open('roundup-card-reference-standalone.html', 'w').write('<!doctype html><html lang="en"><head><meta charset="utf8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>' + page + '</body></html>')

# ---------------- fixture
fx = json.load(open('roundup-card-fixture-r3.json'))
fx['footers'] = dict(only=F8)
json.dump(fx, open('roundup-card-fixture-r4.json', 'w'), indent=1)

# ---------------- companion file
md = rep(md, "revised 9:35pm, 10:00pm and 10:20pm PT after the coordinator's replies and Alex's rulings.", "revised 9:35pm, 10:00pm and 10:20pm PT on Oct 6 and 12:10am PT on Oct 7, after the coordinator's replies and Alex's rulings.")
i = md.index('This is revision 3.'); j = md.index('The rendered reference is')
md = md[:i] + '''This is revision 4. It supersedes revision 3 (`FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006-R3.md` and its folder) and the earlier versions. No card rule, measurement or image has changed since revision 3.

**What changed from revision 3:** Alex ruled that a division that cannot be blended is a matching defect, not a card state, so the proposed "four to seven" footer and the "three of eight" state are withdrawn and their six images removed; Alex ruled that the container uses the product's existing field card and that the tag ink gets a product name; the coordinator's confirmations on the age mark are recorded.

''' + md[j:]
md = rep(md, 'fable-nfl-division-roundup-design-20261006-r3/roundup-card-reference-standalone.html', 'fable-nfl-division-roundup-design-20261006-r4/roundup-card-reference-standalone.html')
anchor = '- **The footer wording is accepted for now.** It can change if it looks wrong in production.'
plain = lambda s: s.replace('<code>', '`').replace('</code>', '`')
md = rep(md, anchor, anchor + '\n' + '\n'.join(f'- **{a}** {plain(b)}' for a, b in NEW_RULINGS))
md = rep(md, 'The coordinator recommends adding a name for it, `--text-secondary-strong`; that is not yet decided and nothing has been added.',
 'Alex ruled that it gets a product name, `--text-secondary-strong`, added as part of the card build.')
FOOT_MD = f'''## The footer line in the product

There is one footer: `{F8}`. Wording accepted by Alex for now. The card appears only when all eight divisions have a verified blend from both venues, so "of 8" is always true when the card is on screen. It fits on one line at 340 wide (see `r3_measure.json`).

If any open division cannot be blended, no card is shown and the feed is unchanged. The coordinator will report such a failure through the existing Flow Sentinel as a matching defect. Revision 3's "four to seven" footer and "three of eight" state are withdrawn. The three-row layout stays in this reference as a layout other round-ups will use.

The headline stays "NFL division front-runners".

Not yet ruled: what the card says late in the season, when a division has been clinched and fewer than eight are still open. That is a settled question, not a data problem.

'''
md = cut(md, '## The footer line in the product', '## When a number is old', FOOT_MD)
md = rep(md, "The two placements are Fable's proposal; the rule and wording are the product's.",
 "The two placements are Fable's proposal; the rule and wording are the product's. The coordinator confirmed on Oct 6 that `PriceAgeMark` can sit in both places unchanged and that the all-old and some-old rule matches `SpecialEventMarkets`. Exact fit is checked on the built card.")
md = rep(md, '`roundup-card-fixture-r3.json` adds the three footer lines and three age cases', '`roundup-card-fixture-r4.json` adds the footer line and three age cases')
md = rep(md, '(named `r3_<state>_light_<width>.png`, 2x; states `all8`, `three3`, `partial`, `old`, `mixed`).', '(named `r3_<state>_light_<width>.png`, 2x; states `all8`, `old`, `mixed`).')
NOT = '''## Not covered

- The selection rule itself (#10354). As recorded by the coordinator after Alex's ruling: all eight divisions must have a verified blend; then the four lowest leader probabilities are shown, highest first.
- The container's layout. Its cards are the product's existing field card, which shows the top three of a division's four teams.
- The matching work that makes the eight blends possible. On Oct 6 no division had a blend, and all eight Polymarket division pages carried a championship label (`fable-evidence-20261006-nfl-division-keys-final.tar.gz`). The coordinator confirmed the classification defect and covers its repair under #10354.
- Late-season wording once a division is clinched.
- The iPhone app. This reference is for the web card.

'''
md = cut(md, '## Not covered', '## Files', NOT)
k = md.index('## Files')
md = md[:k] + '''## Files

In `fable-nfl-division-roundup-design-20261006-r4/`: everything from revision 3 except the six withdrawn images (`r3_three3_*`, `r3_partial_*`), with `roundup-card-reference-standalone.html` rebuilt, plus `build_r4.py`, `build_r4_output.txt`, `r3_page.html` and `r3.md` (the inputs), `roundup-card-fixture-r4.json`, and a new `MANIFEST.json`. `r3_render.html`, `r3_measure.json` and `roundup-card-fixture-r3.json` are kept as the record of how the remaining images were made; they still mention the withdrawn states.
'''
assert '6 covered' not in md and 'four_to_seven' not in json.dumps(fx)
open('FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261007-R4.md', 'w').write(md)
print('page bytes', len(page), 'md bytes', len(md), 'footers', fx['footers'])
