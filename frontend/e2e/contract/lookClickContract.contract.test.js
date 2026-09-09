/**
 * #3968 — the LOOK rail's click contracts, guarded.
 *
 * ## Why this file is not an ordinary test-backlog item
 *
 * The thing under test is **the rail that proves every other lane's
 * rendered-surface work is done** (standing notice 4). When it regresses it does
 * not fail loudly: it goes back to handing out plausible screenshots of the
 * wrong page. Every LOOK taken in the meantime is then unfalsifiable in the
 * failing direction — which is exactly the six-month-class bug #3932 was.
 *
 * #3932 fixed six behaviours and verified all six **by hand against
 * production**. None of it was committed, so the next person to touch
 * `shop-shot.mjs` had no gate at all.
 *
 * ## Why HERE, and what that costs
 *
 * `frontend/jest.config` is rooted at `frontend/` with a `.test.ts(x)` matcher,
 * so nothing under `tools/` is collectable, and bending its `roots` would fight
 * `__tests__/lib/ciJestGate.test.ts`, which guards those settings. The
 * `e2e-contract` job already runs `node --test contract/*.test.js` on every push
 * and sits in `deploy: needs:` — a real gate, needing no install and no network.
 *
 * That home is safe to run unconditionally **because** it launches no browser,
 * and that bounds what can live here. Two of #3932's six behaviours —
 * `.first()` resolving past a `display:none` node, and emoji text (`🏈NFL`) that
 * `getByText(exact)` cannot match — genuinely need Chromium and belong in the
 * browser-audit workflow. They are NOT covered here, and pretending otherwise
 * by asserting on a mock browser would be worse than the gap.
 *
 * What IS here: every decision the rail makes, plus `look.sh`'s exit-code
 * propagation exercised against the real script.
 */

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync, spawnSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const TOOLS = path.join(REPO_ROOT, "tools");
const CONTRACT_MJS = path.join(TOOLS, "shot-click-contract.mjs");
const SHOP_SHOT = path.join(TOOLS, "shop-shot.mjs");
const LOOK_SH = path.join(TOOLS, "look.sh");

/**
 * Strip line and block comments so a source scan tests CODE, not prose.
 *
 * Deliberately crude — it does not understand a `//` inside a string literal —
 * because the alternative is a parser, and every consumer here is asserting the
 * ABSENCE of a construct. A false strip can only ever hide code from the scan
 * in a file this suite also owns, and never invent a violation.
 */
function codeOnly(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
}

/**
 * Load the ESM contract module from CommonJS.
 *
 * `node --test` runs these as CJS, and dynamic `import()` cannot be awaited at
 * describe-time. Rather than restructure every assertion around a promise, ask
 * a child node to import it and hand back the answers as JSON. Slower, but it
 * exercises the REAL module through a REAL ESM import — which also means a
 * syntax error or a bad import inside it reddens here rather than only in
 * production.
 */
function evalInModule(expression) {
  const src = `import * as m from ${JSON.stringify(CONTRACT_MJS)};
process.stdout.write(JSON.stringify((${expression})));`;
  const out = execFileSync(process.execPath, ["--input-type=module", "-e", src], {
    encoding: "utf8",
  });
  return JSON.parse(out);
}

describe("#3968 — the step grammar", () => {
  test("css= and text= are explicit and always beat the shorthand", () => {
    assert.deepEqual(evalInModule('m.readStep("css=a[href=\\"/x\\"]")'), {
      isSelector: true,
      sel: 'a[href="/x"]',
    });
    assert.deepEqual(evalInModule('m.readStep("text=Doubles")'), {
      isSelector: false,
      sel: "Doubles",
    });
  });

  test("a text= target that itself starts with [ stays TEXT", () => {
    // The explicit prefix has to win, or `text=[Live]` becomes a selector and
    // matches nothing — the shorthand would otherwise re-capture it after the
    // prefix is stripped.
    assert.deepEqual(evalInModule('m.readStep("text=[Live]")'), {
      isSelector: false,
      sel: "[Live]",
    });
  });

  test("the [ . # shorthand still reads as a selector", () => {
    for (const step of ["[data-tab=x]", ".pill", "#root"]) {
      assert.equal(
        evalInModule(`m.readStep(${JSON.stringify(step)}).isSelector`),
        true,
        `${step} should be a selector`,
      );
    }
  });

  test("THE #3932 BUG: a bare tag-qualified selector is read as TEXT", () => {
    // This is documented behaviour, not an oversight, and the guard pins it
    // deliberately: `a[href="…"]` starts with `a`, so the shorthand cannot see
    // it. Before #3932 that silently produced a screenshot of the un-tapped
    // page; now it produces a loud CLICKFAIL naming the misreading. If someone
    // "fixes" the heuristic to sniff tag names, this test should be updated
    // CONSCIOUSLY — quietly widening the shorthand is how it swallowed
    // `a[href=…]` in the first place.
    const read = evalInModule('m.readStep("a[href=\\"/sport/football/nfl\\"]")');
    assert.equal(read.isSelector, false);
    assert.match(
      evalInModule("m.clickFailHint(false)"),
      /read as exact TEXT.*css=/s,
      "a text misreading must name itself; a bare timeout cannot be told apart " +
        "from a covered button",
    );
  });

  test("a selector failure carries no text hint", () => {
    // The positive control for the assertion above: if the hint were
    // unconditional, the test above would pass while telling every caller to
    // try `css=` on something already prefixed `css=`.
    assert.equal(evalInModule("m.clickFailHint(true)"), "");
  });

  test("a bare step is text, as the positional argument always was", () => {
    assert.deepEqual(evalInModule('m.readStep("Doubles")'), {
      isSelector: false,
      sel: "Doubles",
    });
  });
});

describe("#3968 — which steps run", () => {
  test("SHOT_CLICKS overrides the positional target AND says so", () => {
    const got = evalInModule(
      'm.parseClickSteps({ envClicks: "Sports;css=nav a", clickText: "Doubles" })',
    );
    assert.deepEqual(got.steps, ["Sports", "css=nav a"]);
    assert.match(got.warning, /overrides the positional click target "Doubles"/);
  });

  test("no warning when there is no conflict", () => {
    assert.equal(
      evalInModule('m.parseClickSteps({ envClicks: "Sports" }).warning'),
      null,
    );
    assert.equal(
      evalInModule('m.parseClickSteps({ clickText: "Doubles" }).warning'),
      null,
    );
  });

  test("blank and whitespace-only steps are dropped, not clicked", () => {
    // `SHOT_CLICKS='Sports;'` is the shape a shell loop produces. An empty step
    // would resolve to `getByText("")`, which matches everything.
    assert.deepEqual(
      evalInModule('m.parseClickSteps({ envClicks: "Sports; ;;  ;css=nav a" }).steps'),
      ["Sports", "css=nav a"],
    );
  });

  test("no clicks at all is an empty list, not a single empty step", () => {
    assert.deepEqual(evalInModule("m.parseClickSteps({}).steps"), []);
    assert.deepEqual(
      evalInModule('m.parseClickSteps({ envClicks: "", clickText: "" }).steps'),
      [],
    );
  });
});

describe("#3968 — SHOT_SCROLL", () => {
  test("unset and empty stay fullPage — the unchanged default", () => {
    assert.deepEqual(evalInModule("m.parseScroll(undefined)"), { mode: "fullPage" });
    assert.deepEqual(evalInModule('m.parseScroll("")'), { mode: "fullPage" });
  });

  test('"top" is offset 0, and a number is that offset', () => {
    assert.deepEqual(evalInModule('m.parseScroll("top")'), { mode: "viewport", y: 0 });
    assert.deepEqual(evalInModule('m.parseScroll("22411")'), {
      mode: "viewport",
      y: 22411,
    });
  });

  test("a typo is a usage ERROR, never a silent fullPage fallback", () => {
    // Falling back would hand back the unreadable 30px strip this option exists
    // to avoid, under a filename saying the caller got the viewport they asked
    // for.
    const got = evalInModule('m.parseScroll("topp")');
    assert.equal(got.mode, "error");
    assert.match(got.message, /must be a number of pixels or "top", got "topp"/);
  });
});

describe("#3968 — the stale artifact is deleted", () => {
  test("an existing PNG at the output path is removed before the run", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "look-stale-"));
    const out = path.join(dir, "shot.png");
    fs.writeFileSync(out, "PRETEND THIS IS LAST RUN'S SCREENSHOT");

    const removed = evalInModule(`m.clearStaleArtifact(${JSON.stringify(out)})`);

    assert.equal(removed, true);
    assert.equal(
      fs.existsSync(out),
      false,
      "the previous run's screenshot is still sitting under this run's filename",
    );
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test("a missing path is not an error and reports nothing removed", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "look-stale-"));
    const out = path.join(dir, "never-existed.png");
    assert.equal(evalInModule(`m.clearStaleArtifact(${JSON.stringify(out)})`), false);
    fs.rmSync(dir, { recursive: true, force: true });
  });
});

describe("#3968 — exit codes are distinct and meaningful", () => {
  test("usage, click-failed and camera are three different values", () => {
    const codes = evalInModule(
      "[m.EXIT_CAMERA, m.EXIT_USAGE, m.EXIT_CLICK_FAILED]",
    );
    assert.deepEqual(codes, [1, 2, 3]);
    assert.equal(new Set(codes).size, 3, "gotcha #124: the VALUE is the story");
  });
});

/**
 * `look.sh` propagation, exercised against the REAL script.
 *
 * The script is copied verbatim into a temp dir beside a stub `shop-shot.mjs`,
 * because `look.sh` resolves its sibling by `dirname "${BASH_SOURCE[0]}"`. So
 * the bytes under test are the real ones; only the dependency is stubbed. `npx`
 * is stubbed on PATH too — the real line is `|| true` and cannot fail the run,
 * but letting it reach the network would break the property that makes the
 * `e2e-contract` job safe to run on every push.
 */
function runLookWith(stubBody, args = ["https://example.test/x"]) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "look-sh-"));
  fs.copyFileSync(LOOK_SH, path.join(dir, "look.sh"));
  fs.chmodSync(path.join(dir, "look.sh"), 0o755);
  fs.writeFileSync(path.join(dir, "shop-shot.mjs"), stubBody);

  const bin = path.join(dir, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, "npx"), "#!/bin/sh\nexit 0\n");
  fs.chmodSync(path.join(bin, "npx"), 0o755);

  const res = spawnSync("bash", [path.join(dir, "look.sh"), ...args], {
    encoding: "utf8",
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}` },
  });
  return { res, dir };
}

describe("#3968 — look.sh propagates the exit code it is given", () => {
  test("exit 3 (a tap that did not land) arrives as 3, not flattened to 1", () => {
    // The whole point of #3932's exit codes. Flattened to 1, "the page you
    // wanted was never reached" is indistinguishable from "the camera broke",
    // and a caller cannot tell whether the PNG it did not get was worth
    // retrying for.
    const { res, dir } = runLookWith('process.exit(3);\n');
    assert.equal(res.status, 3, `look.sh flattened the exit code (stderr: ${res.stderr})`);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test("exit 2 (usage) arrives as 2", () => {
    const { res, dir } = runLookWith('process.exit(2);\n');
    assert.equal(res.status, 2);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test("a run that writes no PNG fails even when the child exits 0", () => {
    // The ux/976 lesson: the old rail exited 0 while producing no file, so a
    // dead camera read as a clean pass.
    const { res, dir } = runLookWith('process.exit(0);\n');
    assert.notEqual(res.status, 0, "a dead camera reported a clean pass");
    assert.match(res.stderr, /no screenshot written/);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test("the success path writes the PNG and prints its path", () => {
    // The positive control. Without it, a look.sh that failed unconditionally
    // would satisfy all three assertions above.
    const stub = `import { writeFileSync } from 'fs';
writeFileSync(process.argv[3], 'PNGBYTES');
process.exit(0);
`;
    const { res, dir } = runLookWith(stub, [
      "https://example.test/x",
      path.join(os.tmpdir(), `look-ok-${process.pid}.png`),
    ]);
    assert.equal(res.status, 0, `stderr: ${res.stderr}`);
    assert.match(res.stdout.trim(), /look-ok-.*\.png$/);
    fs.rmSync(res.stdout.trim(), { force: true });
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test("a multi-word click target survives as ONE argument", () => {
    // ux/1052: `$CLICK` was unquoted, so "AL / NL Champ" arrived as four argv
    // entries and only the first word was ever used — CLICKFAIL, then a
    // screenshot of the un-clicked page, which read as a clean pass.
    const stub = `import { writeFileSync } from 'fs';
writeFileSync(process.argv[3], JSON.stringify(process.argv.slice(4)));
process.exit(0);
`;
    const out = path.join(os.tmpdir(), `look-argv-${process.pid}.png`);
    const { res, dir } = runLookWith(stub, [
      "https://example.test/x",
      out,
      "AL / NL Champ",
    ]);
    assert.equal(res.status, 0, `stderr: ${res.stderr}`);
    assert.deepEqual(JSON.parse(fs.readFileSync(out, "utf8")), ["AL / NL Champ"]);
    fs.rmSync(out, { force: true });
    fs.rmSync(dir, { recursive: true, force: true });
  });
});

describe("#4408 — the shot carries no fabricated :hover", () => {
  // The rail never moved the mouse. Playwright's pointer starts at (0,0) and
  // stays where a click left it, so SHOT_SCROLL scrolls content under a
  // stationary pointer and photographs whatever lands there in `:hover`.
  // Measured on /tournaments/us-open at 390px: `SHOT_CLICKS="Men's"` +
  // `SHOT_SCROLL=900` painted one finished match grey, in three disjoint
  // blocks with a white seam, while its identical siblings stayed white. A DOM
  // census found NO element with a grey background — so it was invisible to a
  // probe and visible only in the PNG, which is the worst pairing there is for
  // a rule that says "screenshot it and judge it".

  test("the park point is outside the viewport, at every size the rail is used at", () => {
    // The property, not the number. (0,0) hovers the logo and (2,2) still
    // hovers the sticky header — both measured — so an edit to either of those
    // "obviously fine" corners has to fail here.
    const viewports = [
      { width: 390, height: 844 }, // the phone-width LOOK, and the measured case
      { width: 1280, height: 2200 }, // shop-shot's defaults
      { width: 1, height: 1 },
      { width: 3000, height: 4000 },
    ];
    for (const vp of viewports) {
      const p = evalInModule(`m.pointerParkPoint(${JSON.stringify(vp)})`);
      assert.ok(
        p.x < 0 && p.y < 0,
        `park point ${JSON.stringify(p)} is inside ${vp.width}x${vp.height}; ` +
          "a pointer anywhere in the viewport hovers something, and on a " +
          "phone-width shot of a touch surface a hover state is never evidence",
      );
    }
  });

  test("a missing or nonsense viewport still parks outside", () => {
    // shop-shot parses W/H out of the environment, so NaN is reachable from a
    // typo. Falling back to (0,0) there would restore the bug precisely on the
    // path nobody tests by hand.
    for (const arg of ["", "{}", '{width: NaN, height: NaN}', "{width: -5, height: 0}"]) {
      const p = evalInModule(`m.pointerParkPoint(${arg || "undefined"})`);
      assert.ok(p.x < 0 && p.y < 0, `pointerParkPoint(${arg}) returned ${JSON.stringify(p)}`);
    }
  });

  test("parking is the default, and the opt-out is explicit", () => {
    assert.equal(evalInModule("m.shouldParkPointer(undefined)"), true);
    assert.equal(evalInModule("m.shouldParkPointer('')"), true);
    assert.equal(evalInModule("m.shouldParkPointer('0')"), true);
    // A lane photographing a hover-only affordance needs the pointer left
    // alone; removing that capability would trade one blind spot for another.
    assert.equal(evalInModule("m.shouldParkPointer('1')"), false);
    assert.equal(evalInModule("m.shouldParkPointer('true')"), false);
  });

  test("shop-shot parks the pointer BEFORE the shutter, not after", () => {
    // A pure function nobody calls proves nothing about reach, and a park that
    // happens after the screenshot is exactly as useless as no park at all.
    // Ordering is the whole property, so it is asserted on positions rather
    // than on the presence of a line.
    const src = codeOnly(fs.readFileSync(SHOP_SHOT, "utf8"));
    const park = src.indexOf("pointerParkPoint(");
    const move = src.indexOf("mouse.move(");
    const shot = src.indexOf("page.screenshot(");
    assert.ok(park !== -1, "shop-shot.mjs never calls pointerParkPoint()");
    assert.ok(move !== -1, "shop-shot.mjs never moves the pointer");
    assert.ok(
      src.includes("shouldParkPointer("),
      "shop-shot.mjs ignores shouldParkPointer(), so SHOT_KEEP_POINTER does nothing",
    );
    assert.ok(shot !== -1, "shop-shot.mjs takes no screenshot");
    assert.ok(
      move < shot,
      "the pointer is parked after the first page.screenshot() — the shot it " +
        "was meant to protect is already taken",
    );
    // Hover is recomputed at the pointer's position on every scroll, so the
    // park must also precede the scroll that SHOT_SCROLL performs.
    const scrollTo = src.indexOf("window.scrollTo(");
    assert.ok(
      scrollTo === -1 || move < scrollTo,
      "the pointer is parked after the SHOT_SCROLL scroll; content scrolled " +
        "under a stationary pointer is what fabricated the hover in the first place",
    );
  });
});

describe("#3968 — the extraction cannot rot", () => {
  test("shop-shot.mjs CALLS the extracted logic rather than keeping a copy", () => {
    // Without this, every assertion above can stay green while `shop-shot.mjs`
    // quietly reverts to its own inline copy of the grammar — the module would
    // be tested, and the rail would be running something else. This is the same
    // trap `jestGate.contract.test.js` exists for: a guard that cannot see
    // whether the thing it guards is still wired in.
    const src = fs.readFileSync(SHOP_SHOT, "utf8");

    assert.match(
      src,
      /from '\.\/shot-click-contract\.mjs'/,
      "shop-shot.mjs no longer imports the contract module",
    );
    for (const fn of ["readStep(", "parseClickSteps(", "parseScroll(", "clearStaleArtifact("]) {
      assert.ok(src.includes(fn), `shop-shot.mjs never calls ${fn}`);
    }
    assert.ok(
      !/isSelector\s*=\s*\/\^\[\[\.#\]\//.test(src),
      "the inline step-grammar regex is back in shop-shot.mjs — the extracted " +
        "module is now decorative and this suite guards nothing",
    );
  });

  test("the contract module launches no browser and reads no process state", () => {
    // The property that lets this suite run in the no-install, no-network,
    // no-browser `e2e-contract` job. A stray playwright import here would make
    // the job need a browser download and it would stop being unconditional.
    //
    // Scanned over CODE ONLY. The first cut scanned the raw file and went red
    // on the module's own docstring, which says "no `process.env`, no
    // `process.argv`" — the guard cannot tell a banned call from prose
    // ABOUT the banned call, so documenting the rule broke the rule. Stripping
    // comments is not cosmetic here: it is the difference between a guard on
    // behaviour and a guard on wording.
    const src = codeOnly(fs.readFileSync(CONTRACT_MJS, "utf8"));
    assert.ok(!/playwright/i.test(src), "the contract module imports playwright");
    assert.ok(
      !/process\.(env|argv)/.test(src),
      "the contract module reads process state; it must be a pure function of " +
        "its arguments so the caller's environment cannot change its answers",
    );
  });
});
