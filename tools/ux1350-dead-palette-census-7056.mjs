#!/usr/bin/env node
/**
 * #7056 / #4040 after-check probe: are the emerald/amber/slate numeric utilities
 * actually EMITTED in built CSS?
 *
 * The defect is silent by construction — the element renders, just with no colour —
 * so source greps, `npm run build`, typecheck and jest are all green while the class
 * emits nothing. The ONLY witness is the built stylesheet.
 *
 * Usage:  node tools/ux1350-dead-palette-census-7056.mjs [cssDir]
 *   exit 0 = every family that source asks for by number is emitted  (FIXED)
 *   exit 3 = at least one family is asked for by number and emits ZERO rules (DEFECT)
 *   exit 4 = no CSS found to read — nothing was checked, NOT a pass
 */
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { execSync } from 'node:child_process';

const cssDir = process.argv[2] || '.next/static/css';
const FAMILIES = ['emerald', 'amber', 'slate'];

if (!existsSync(cssDir)) {
  console.error(`exit 4: no CSS at ${cssDir} — run \`npm run build\` first. NOTHING WAS CHECKED.`);
  process.exit(4);
}
const files = readdirSync(cssDir).filter((f) => f.endsWith('.css'));
if (files.length === 0) {
  console.error(`exit 4: ${cssDir} holds no .css — NOTHING WAS CHECKED.`);
  process.exit(4);
}
const css = files.map((f) => readFileSync(join(cssDir, f), 'utf8')).join('\n');
console.log(`read ${files.length} stylesheet(s), ${css.length} bytes from ${cssDir}`);

// What does SOURCE ask for, by number?
const srcCount = (fam) => {
  const out = execSync(
    `/usr/bin/grep -rhoE '\\b(bg|text|border|ring|from|via|to|divide|fill|stroke)-${fam}-[0-9]{2,3}\\b' app components lib || true`,
    { encoding: 'utf8' }
  );
  return out.split('\n').filter(Boolean).length;
};

let defect = false;
console.log('\nfamily   | asked for by source | emitted in CSS');
console.log('---------|---------------------|---------------');
for (const fam of FAMILIES) {
  const asked = srcCount(fam);
  const emitted = (css.match(new RegExp(`\\.[a-zA-Z0-9:\\\\/\\[\\]().%-]*${fam}-[0-9]{2,3}[^a-zA-Z0-9-]`, 'g')) || []).length;
  const bad = asked > 0 && emitted === 0;
  if (bad) defect = true;
  console.log(
    `${fam.padEnd(8)} | ${String(asked).padStart(19)} | ${String(emitted).padStart(14)}${bad ? '   <-- DEAD' : ''}`
  );
}

// Control: a family nobody overrode must be present, or the probe itself is broken.
const control = (css.match(/\.[a-zA-Z0-9:\\/\[\]().%-]*lime-[0-9]{2,3}[^a-zA-Z0-9-]/g) || []).length;
const limeAsked = srcCount('lime');
console.log(`\ncontrol: source asks for ${limeAsked} lime-N, CSS emits ${control}`);
if (limeAsked > 0 && control === 0) {
  console.error('exit 4: the CONTROL family is also missing — the probe is reading the wrong CSS. NOTHING WAS CHECKED.');
  process.exit(4);
}

console.log(defect ? '\nexit 3: DEFECT — a family is asked for by number and emits nothing'
                   : '\nexit 0: every numerically-referenced family is emitted');
process.exit(defect ? 3 : 0);
