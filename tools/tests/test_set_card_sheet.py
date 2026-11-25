"""Tests for tools/set-card-sheet.mjs argument parsing, slug selection, and CLI guards."""

import json
import subprocess
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "set-card-sheet.mjs"


def run_node_helper(js_code: str) -> subprocess.CompletedProcess[str]:
    script = f"import * as mod from {json.dumps(TOOL.as_uri())};\n{js_code}"
    return subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )


class SetCardSheetTests(unittest.TestCase):
    def test_parse_args_accepts_flags_and_slugs(self) -> None:
        proc = run_node_helper(
            "const out = mod.parseArgs(['--out', '/tmp/s.png', '--feed-json', '/tmp/f.json', '--web-url', 'http://localhost:3000/discover', '--scale', '1', 'machinery-a', 'machinery-b']);"
            "console.log(JSON.stringify(out));"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertEqual(parsed["out"], "/tmp/s.png")
        self.assertEqual(parsed["feedJson"], "/tmp/f.json")
        self.assertEqual(parsed["webUrl"], "http://localhost:3000/discover")
        self.assertEqual(parsed["scale"], 1)
        self.assertEqual(parsed["slugs"], ["machinery-a", "machinery-b"])

    def test_parse_args_rejects_missing_out_and_missing_slugs(self) -> None:
        p_no_out = run_node_helper("mod.parseArgs(['machinery-a']);")
        self.assertNotEqual(p_no_out.returncode, 0)
        self.assertIn("--out", p_no_out.stderr)

        p_no_slugs = run_node_helper("mod.parseArgs(['--out', '/tmp/a.png']);")
        self.assertNotEqual(p_no_slugs.returncode, 0)
        self.assertIn("slug", p_no_slugs.stderr)

    def test_select_cards_preserves_cli_order_and_fails_on_missing_slug(self) -> None:
        js = """
        const payloads = [
          { items: [{ data: { collection_ref: { slug: 'machinery-b' }, title: 'B' } }] },
          { items: [
            { data: { collection_ref: { slug: 'machinery-a' }, title: 'A' } },
            { data: { collection_ref: { slug: 'machinery-b' }, title: 'B-dup' } },
          ] },
        ];
        const res = mod.selectCardsBySlug(payloads, ['machinery-a', 'machinery-b']);
        console.log(JSON.stringify(res.items.map(i => i.data.title)));
        """
        proc = run_node_helper(js)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), ["A", "B"])

        p_missing = run_node_helper(
            "mod.selectCardsBySlug([{ items: [{ data: { collection_ref: { slug: 'machinery-a' } } }] }], ['machinery-a', 'machinery-missing']);"
        )
        self.assertNotEqual(p_missing.returncode, 0)
        self.assertIn("machinery-missing", p_missing.stderr)


if __name__ == "__main__":
    unittest.main()
