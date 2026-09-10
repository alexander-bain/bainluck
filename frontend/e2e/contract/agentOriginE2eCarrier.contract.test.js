/**
 * Notice 39 / #4763 — the E2E rail's own agent-origin carrier, guarded.
 *
 * `agentOriginCarriers.contract.test.js` pins the SHELL carrier (rung 1). This pins
 * the Node one, and the two are deliberately separate files: they are different
 * carriers with different failure modes, and one file that greens on either half is
 * exactly the "repaired copy hides the broken one" shape gotcha #128 names.
 *
 * ## Why this needs a test rather than care
 *
 * The failure is silent and directional, as it is everywhere in this family: an
 * absent header is read by the backend as a PERSON (`if not raw`). There is no
 * error and no 4xx — the call simply goes back to writing a row that says a person
 * searched `grand prix`, while its author has every reason to believe it is tagged.
 * That is what was happening 51 times in thirty days before #4763.
 *
 * The SECOND failure mode is the over-correction, and it is why the leak tests
 * below are not decoration: "tag everything" passes any test that only checks our
 * own host, and it puts an internal header naming our lanes on a third party's
 * wire.
 */

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  ORIGIN_HEADER,
  ORIGIN_USER,
  resolveAgent,
  isOurHost,
  originHeaders,
  tagged,
} = require("../helpers/agentOrigin");

const OURS = "https://api.bainluck.com/api/events/search?q=tennis";

/** Run `fn` with `env` applied, then restore. Node has no scoped-env primitive. */
function withEnv(env, fn) {
  const saved = {};
  for (const [k, v] of Object.entries(env)) {
    saved[k] = process.env[k];
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
  try {
    return fn();
  } finally {
    for (const [k, v] of Object.entries(saved)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  }
}

/** The clean slate every case starts from: no name, and not inside Actions. */
const BARE = { BL_AGENT: undefined, GITHUB_ACTIONS: undefined, GITHUB_WORKFLOW: undefined };

describe("the wire name agrees with the backend", () => {
  test("ORIGIN_HEADER is character-for-character what routes/events.py reads", () => {
    // A sender and a reader that disagree by one character produce NO error
    // anywhere: every probe looks tagged, every row is still written, and the
    // drift is invisible until someone counts. Read the Python constant rather
    // than restating it here, or this test just agrees with itself.
    const py = fs.readFileSync(
      path.resolve(__dirname, "..", "..", "..", "backend", "app", "utils", "agent_origin.py"),
      "utf8",
    );
    const m = py.match(/^ORIGIN_HEADER\s*=\s*"([^"]+)"/m);
    assert.ok(m, "could not find ORIGIN_HEADER in agent_origin.py");
    assert.equal(ORIGIN_HEADER, m[1]);

    const u = py.match(/^ORIGIN_USER\s*=\s*"([^"]+)"/m);
    assert.ok(u, "could not find ORIGIN_USER in agent_origin.py");
    assert.equal(ORIGIN_USER, u[1]);
  });
});

describe("naming", () => {
  test("BL_AGENT wins when set", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      assert.equal(resolveAgent(), "lane-x");
      assert.equal(originHeaders(OURS)[ORIGIN_HEADER], "lane-x");
    });
  });

  test("BL_AGENT=user is honoured verbatim — the one value that KEEPS the row", () => {
    withEnv({ ...BARE, BL_AGENT: "user" }, () => {
      assert.equal(originHeaders(OURS)[ORIGIN_HEADER], ORIGIN_USER);
    });
  });

  test("a human running a pack locally is NOT tagged", () => {
    // Guard 1, and the direction is the whole point: any non-"user" value
    // SUPPRESSES the search-log row, so tagging on absence would delete real
    // people from the table this exists to clean.
    for (const env of [{}, { BL_AGENT: "" }, { BL_AGENT: "   " }]) {
      withEnv({ ...BARE, ...env }, () => {
        assert.equal(resolveAgent(), null);
        assert.deepEqual(originHeaders(OURS), {});
      });
    }
  });

  test("inside GitHub Actions the runner names itself, without any workflow edit", () => {
    withEnv({ ...BARE, GITHUB_ACTIONS: "true", GITHUB_WORKFLOW: "Browser audit" }, () => {
      assert.equal(resolveAgent(), "ci:browser-audit");
    });
  });

  test("a workflow with no name still yields a real, non-empty tag", () => {
    // The third state is the only one that lies: an EMPTY header reads as a
    // person at the backend while looking tagged to its author.
    for (const wf of [undefined, "", "   ", "!!!"]) {
      withEnv({ ...BARE, GITHUB_ACTIONS: "true", GITHUB_WORKFLOW: wf }, () => {
        const who = resolveAgent();
        assert.ok(who && who.trim().length > 0, `empty tag for workflow ${JSON.stringify(wf)}`);
      });
    }
  });

  test("GITHUB_ACTIONS is honoured only when it literally says true", () => {
    // `process.env.GITHUB_ACTIONS` is a string. A truthiness test would tag on
    // the string "false", which is what a non-Actions harness that sets the var
    // defensively would produce.
    for (const v of ["false", "0", "", "TRUE", "yes"]) {
      withEnv({ ...BARE, GITHUB_ACTIONS: v }, () => {
        assert.equal(resolveAgent(), null, `tagged on GITHUB_ACTIONS=${JSON.stringify(v)}`);
      });
    }
  });

  test("BL_AGENT outranks the Actions deduction", () => {
    withEnv({ ...BARE, BL_AGENT: "user", GITHUB_ACTIONS: "true", GITHUB_WORKFLOW: "Browser audit" }, () => {
      assert.equal(resolveAgent(), ORIGIN_USER);
    });
  });
});

describe("host scoping — the over-correction guard", () => {
  test("never sends the header to a host that is not ours", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      for (const url of [
        "https://api.elections.kalshi.com/trade-api/v2/events",
        "https://gamma-api.polymarket.com/events",
        "https://api.github.com/repos/alexander-bain/bainluck",
        "https://site.api.espn.com/apis/site/v2/sports",
      ]) {
        assert.deepEqual(originHeaders(url), {}, `leaked an internal header to ${url}`);
        assert.equal(isOurHost(url), false);
      }
    });
  });

  test("a lookalike host does not get the header — HOST match, not substring", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      // The case a naive `url.includes("bainluck.com")` passes and must not.
      for (const url of [
        "https://example.com/?ref=bainluck.com",
        "https://bainluck.com.evil.test/api/feed",
        "https://notbainluck.com/api/feed",
      ]) {
        assert.deepEqual(originHeaders(url), {}, `leaked to lookalike ${url}`);
      }
    });
  });

  test("our own hosts and their subdomains ARE tagged — the scoping must not be a no-op", () => {
    // Without this, deleting the whole tagging branch would go green.
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      for (const url of [
        "https://api.bainluck.com/api/feed",
        "https://www.bainluck.com/discover",
        "https://bainluck.com/",
        "http://localhost:8000/api/feed",
        "http://127.0.0.1:8000/api/feed",
      ]) {
        assert.equal(originHeaders(url)[ORIGIN_HEADER], "lane-x", `failed to tag ${url}`);
      }
    });
  });

  test("an unparseable URL is not ours", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      for (const url of ["", "::::", "http://"]) {
        assert.deepEqual(originHeaders(url), {});
      }
    });
  });
});

describe("merging", () => {
  test("the caller's explicit origin always wins, and is never duplicated", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      const out = tagged(OURS, { "x-bainluck-origin": "mine" });
      assert.equal(out["x-bainluck-origin"], "mine");
      const origins = Object.keys(out).filter((k) => k.toLowerCase() === ORIGIN_HEADER);
      assert.equal(origins.length, 1, `two disagreeing origin headers: ${JSON.stringify(out)}`);
    });
  });

  test("a caller's origin wins whatever its CASE — headers are case-insensitive", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      const out = tagged(OURS, { "X-BainLuck-Origin": "mine" });
      assert.equal(out["X-BainLuck-Origin"], "mine");
      assert.equal(out[ORIGIN_HEADER], undefined, `added a second origin: ${JSON.stringify(out)}`);
    });
  });

  test("a caller's User-Agent is never clobbered", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      const out = tagged(OURS, { "User-Agent": "custom/9" });
      assert.equal(out["User-Agent"], "custom/9");
    });
  });

  test("the caller's other headers survive untouched", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      const out = tagged(OURS, { Accept: "application/json" });
      assert.equal(out.Accept, "application/json");
      assert.equal(out[ORIGIN_HEADER], "lane-x");
      assert.equal(out["User-Agent"], "BainLuckBot/1.0 (lane-x)");
    });
  });

  test("tagged() does not mutate the headers it was given", () => {
    withEnv({ ...BARE, BL_AGENT: "lane-x" }, () => {
      const mine = { Accept: "application/json" };
      tagged(OURS, mine);
      assert.deepEqual(mine, { Accept: "application/json" });
    });
  });

  test("an untagged caller gets its headers back unchanged, not a bot UA", () => {
    // Both halves matter: a `BainLuckBot/1.0` UA with no origin header is a
    // request that looks automated in the router log while still writing the
    // row — the worst of both readings.
    withEnv({ ...BARE }, () => {
      assert.deepEqual(tagged(OURS, { Accept: "application/json" }), { Accept: "application/json" });
    });
  });

  test("the name is read at CALL time, never captured at import", () => {
    // A name baked in at load is wrong for any caller that sets BL_AGENT after
    // the module is required, and the failure is silent in both directions.
    withEnv({ ...BARE, BL_AGENT: "first" }, () => {
      assert.equal(originHeaders(OURS)[ORIGIN_HEADER], "first");
    });
    withEnv({ ...BARE, BL_AGENT: "second" }, () => {
      assert.equal(originHeaders(OURS)[ORIGIN_HEADER], "second");
    });
  });
});

describe("the call sites really use the carrier (#4763's own regression)", () => {
  // 🔴 Every assertion above can pass while no spec calls the helper at all —
  // that is precisely the state production was in before this issue. So the
  // specs that reach our API are checked for the wiring, with comments stripped
  // so a file that merely DISCUSSES the carrier cannot satisfy the guard.
  const SPECS = path.resolve(__dirname, "..", "specs");

  /**
   * Strip comments — LINE comments first, and that order is load-bearing.
   *
   * 🔴 Doing blocks first is the obvious order and it is wrong, as this file's own
   * first run proved: a line comment in `event-page.spec.ts` mentioned an API path
   * ending `/*`, which opened a block comment that swallowed 166 lines of REAL
   * CODE — including the very call this guard exists to check. The test failed
   * loudly there, but the same bug in the other direction (eating a bare,
   * untagged call) would have made the scan below pass while examining nothing.
   * `agentOriginCarriers.contract.test.js` strips blocks first and shares the
   * latent bug; it survives only because its target's prose happens not to
   * contain the sequence.
   */
  function sourceOf(name) {
    return fs
      .readFileSync(path.join(SPECS, name), "utf8")
      .split("\n")
      .map((l) => l.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n")
      .replace(/\/\*[\s\S]*?\*\//g, "");
  }

  test("stripping removes prose and KEEPS code — the anti-vacuity check", () => {
    // Two directions, because only the second one fails safely. If prose survives,
    // a file that merely discusses the carrier satisfies the guard. If CODE is
    // eaten, the scan below inspects a shorter file and greens on nothing.
    const stripped = sourceOf("tournament-inventory.spec.ts");
    assert.ok(!stripped.includes("51 of 51"), "comment stripping regressed — prose survived");

    for (const [name, landmark] of [
      ["tournament-inventory.spec.ts", "journey.finish("],
      ["search-answer.spec.ts", "page.request.get("],
      ["league-cards.spec.ts", "leagueOwed("],
      ["event-page.spec.ts", "findSettledEventWithProps("],
    ]) {
      assert.ok(
        sourceOf(name).includes(landmark),
        `stripping ate real code in ${name} — "${landmark}" is gone, so every assertion here is vacuous`,
      );
    }
  });

  for (const name of [
    "tournament-inventory.spec.ts",
    "search-answer.spec.ts",
    "league-cards.spec.ts",
    "event-page.spec.ts",
  ]) {
    test(`${name} imports the carrier and passes its headers`, () => {
      const code = sourceOf(name);
      assert.match(code, /from\s+"\.\.\/helpers\/agentOrigin"/, `${name} does not import the carrier`);
      assert.match(code, /headers:\s*tagged\(/, `${name} imports the carrier but never passes its headers`);
    });
  }

  test("no spec reaching our API still makes a bare, untagged request", () => {
    // The drift this catches: a NEW call site added beside a tagged one. A file
    // may only contain a `page.request.get`/`fetch` on an API-base URL if that
    // same call passes `headers:`.
    for (const name of fs.readdirSync(SPECS).filter((f) => f.endsWith(".spec.ts"))) {
      const code = sourceOf(name);
      // Calls built from the API base, on one line, that carry no `headers:`.
      const bare = code
        .split("\n")
        .filter((l) => /(page\.request\.(get|post)|[^.\w]fetch)\s*\(/.test(l))
        .filter((l) => /API_BASE|apiBase|\(url\)/.test(l))
        .filter((l) => !/headers:/.test(l));
      assert.deepEqual(bare, [], `${name} has an untagged own-host request: ${JSON.stringify(bare)}`);
    }
  });
});
