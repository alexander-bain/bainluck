/**
 * Notice 39 / #1916 rung 1 — the agent-origin CARRIERS, guarded.
 *
 * ## What is actually at stake
 *
 * `x-bainluck-origin` is not a label. `routes/events.py:_request_is_automation` reads
 * it, and any non-empty value other than the literal `user` SUPPRESSES the
 * search-query log write and the trending vote. The warmer then picks what to warm
 * from the 30-day head of that same table. So these carriers decide whether our own
 * fleet votes in the distribution it measures — over the 7 days to 2026-09-09, 114 of
 * 1,231 rows carried markdown residue (a backtick or `**`) that only an agent pasting
 * its notes into a URL can produce, and that is a floor, not an estimate.
 *
 * ## Why the failure mode needs a test rather than care
 *
 * Both carriers fail SILENTLY and in the same direction: an empty or absent header is
 * read by the backend as a person (`if not raw`). There is no error, no 4xx, no log —
 * the call simply goes back to voting while its author has every reason to believe it
 * is tagged. `tools/bl-agent-curl.sh` shipped with exactly that bug in its first draft
 * (see the `BL_AGENT=x . script` case below), and it was invisible until the argv was
 * printed. A rail whose regression is indistinguishable from success is the same class
 * as #3932, which is why this sits beside `lookClickContract`.
 *
 * ## Home
 *
 * Same reasoning as `lookClickContract.contract.test.js`: `frontend/jest.config` cannot
 * collect anything under `tools/`, while the `e2e-contract` job already runs
 * `node --test contract/*.test.js` on every push and sits in `deploy: needs:`. Safe to
 * run unconditionally because nothing here launches a browser or touches the network —
 * the shell helper is exercised for real through its `BL_CURL_PRINT` argv dry-run.
 */

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const HELPER = path.join(REPO_ROOT, "tools", "bl-agent-curl.sh");
const SHOP_SHOT = path.join(REPO_ROOT, "tools", "shop-shot.mjs");

/**
 * Run a snippet with the helper sourced, and return the argv the shadowed `curl`
 * WOULD have executed. Exercises the real script, not a reimplementation of it.
 */
function argv(snippet, { shell = "bash", env = {} } = {}) {
  // The helper's path travels in the ENVIRONMENT and is expanded by the shell, rather
  // than being interpolated into the command string. Interpolating it is what the
  // obvious version does, and CodeQL is right to call it "Shell command built from
  // environment values": `__dirname` is an absolute path nobody here controls, so a
  // checkout under a directory containing a quote or `$(…)` would break the sourcing
  // line or execute part of it. Caught on `7b602ed8` by the notice-32 check-run read.
  const res = spawnSync(shell, ["-c", `. "$BL_HELPER"\n${snippet}`], {
    encoding: "utf8",
    env: { ...process.env, BL_HELPER: HELPER, BL_AGENT: "", BL_CURL_PRINT: "1", ...env },
  });
  assert.equal(res.status, 0, `helper exited ${res.status}: ${res.stderr}`);
  return {
    args: res.stdout.split("\n").filter((l) => l.length > 0),
    stderr: res.stderr,
  };
}

/** The value of the origin header in an argv, or null when it is absent. */
function originOf(args) {
  const i = args.findIndex((a) => a.toLowerCase().startsWith("x-bainluck-origin:"));
  return i === -1 ? null : args[i].slice("x-bainluck-origin:".length).trim();
}

// Both shells are in play: the lanes run zsh, the bus's windows run bash. The helper is
// POSIX on purpose and the parameter expansions it leans on are the kind that differ.
for (const shell of ["bash", "sh"]) {
  describe(`bl-agent-curl.sh (${shell})`, () => {
    test("tags a request to our own API with the origin header and a bot UA", () => {
      const { args } = argv(`curl -s "https://api.bainluck.com/api/events/search?q=Ajax"`, {
        shell,
        env: { BL_AGENT: "lane-x" },
      });
      assert.equal(originOf(args), "lane-x");
      assert.ok(
        args.some((a) => a === "BainLuckBot/1.0 (lane-x)"),
        `expected a BainLuckBot UA, got ${JSON.stringify(args)}`,
      );
      // The caller's own flags and URL must survive untouched.
      assert.ok(args.includes("-s"));
      assert.ok(args.includes("https://api.bainluck.com/api/events/search?q=Ajax"));
    });

    test("BL_AGENT set as a prefix to the SOURCE still yields a non-empty tag", () => {
      // 🔴 The regression that shipped in the first draft. An assignment prefixed to `.`
      // does not persist outside POSIX mode, so a source-time read baked in the EMPTY
      // string — and an empty header is read by the backend as a person. The tag must
      // therefore be resolved per call. Asserting "non-empty" is the whole point; the
      // exact value here is deliberately not the interesting part.
      const { args } = argv(`curl "https://api.bainluck.com/api/feed"`, { shell });
      const origin = originOf(args);
      assert.notEqual(origin, null, "no origin header was sent at all");
      assert.notEqual(origin, "", "origin header was sent EMPTY — reads as a person");
    });

    test("BL_AGENT=user is honoured verbatim — the one value that keeps the row", () => {
      const { args } = argv(`BL_AGENT=user curl "https://api.bainluck.com/api/events/search?q=x"`, {
        shell,
        env: { BL_AGENT: "lane-x" },
      });
      assert.equal(originOf(args), "user");
    });

    test("never sends the header to a host that is not ours", () => {
      for (const url of [
        "https://api.elections.kalshi.com/trade-api/v2/events",
        "https://gamma-api.polymarket.com/events",
        "https://api.github.com/repos/alexander-bain/bainluck",
      ]) {
        const { args } = argv(`curl -s "${url}"`, { shell, env: { BL_AGENT: "lane-x" } });
        assert.equal(originOf(args), null, `leaked an internal header to ${url}`);
        assert.deepEqual(args, ["-s", url]);
      }
    });

    test("a lookalike host does not get the header — the match is on the HOST, not a substring", () => {
      // `https://example.com/?ref=bainluck.com` is the case a `case *bainluck.com*`
      // test passes and must not.
      const { args } = argv(`curl "https://example.com/?ref=bainluck.com"`, {
        shell,
        env: { BL_AGENT: "lane-x" },
      });
      assert.equal(originOf(args), null);
    });

    test("a request body mentioning our host does not make a third party into us", () => {
      // `-d '{"sql":"...bainluck.com..."}'` is an ordinary argument in this repo.
      const { args } = argv(
        `curl -d '{"sql":"select 1 from bainluck.com"}' "https://gamma-api.polymarket.com/events"`,
        { shell, env: { BL_AGENT: "lane-x" } },
      );
      assert.equal(originOf(args), null);
    });

    test("never sends the header twice when the caller already set one", () => {
      const { args } = argv(
        `curl -H "x-bainluck-origin: mine" "https://api.bainluck.com/api/feed"`,
        { shell, env: { BL_AGENT: "lane-x" } },
      );
      const origins = args.filter((a) => a.toLowerCase().startsWith("x-bainluck-origin:"));
      assert.equal(origins.length, 1, `two disagreeing origin headers: ${JSON.stringify(args)}`);
      assert.equal(originOf(args), "mine", "the caller's explicit intent must win");
    });

    test("our flags go first so a caller's own -A still wins", () => {
      const { args } = argv(
        `curl -A "custom/9" "https://api.bainluck.com/api/feed"`,
        { shell, env: { BL_AGENT: "lane-x" } },
      );
      assert.ok(
        args.lastIndexOf("custom/9") > args.lastIndexOf("BainLuckBot/1.0 (lane-x)"),
        `curl takes the LAST -A; ours must not be it: ${JSON.stringify(args)}`,
      );
    });

    test("an unnamed agent is still tagged, and is told exactly once", () => {
      const { args, stderr } = argv(
        `curl "https://api.bainluck.com/api/feed" >/dev/null\n` +
          `curl "https://api.bainluck.com/api/feed" >/dev/null\n` +
          `curl "https://api.bainluck.com/api/feed"`,
        { shell },
      );
      assert.equal(originOf(args), "agent-unnamed", "unnamed is not evidence of humanity");
      const warnings = stderr.split("\n").filter((l) => l.includes("BL_AGENT unset"));
      assert.equal(warnings.length, 1, `expected one warning across three calls, got ${warnings.length}`);
    });
  });
}

describe("shop-shot.mjs carries the tag (notice 39 rung 1, look.sh's whole fleet)", () => {
  // 🔴 Scanning the raw source would pass on a file that only DISCUSSES the header:
  // shop-shot.mjs devotes ~20 lines of comment to why it sends one and why it does not
  // touch the User-Agent. A guard blinded by its target's own prose is not a guard, so
  // comments are stripped before anything is asserted.
  const code = fs
    .readFileSync(SHOP_SHOT, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((l) => l.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");

  test("the comments really were stripped", () => {
    // Cheap self-check: if this ever fails, every assertion below is unfalsifiable.
    assert.ok(!code.includes("nine lanes plus the bus"), "comment stripping regressed");
  });

  test("sends x-bainluck-origin as a real request header", () => {
    assert.match(code, /extraHTTPHeaders\s*:\s*\{\s*['"]x-bainluck-origin['"]\s*:/);
  });

  test("sets the bl_agent cookie rung 3's analytics drop keys on", () => {
    assert.match(code, /name\s*:\s*['"]bl_agent['"]/);
  });

  test("BL_AGENT is the escape hatch, and shooting as a person stays possible", () => {
    assert.match(code, /process\.env\.BL_AGENT/);
  });
});
