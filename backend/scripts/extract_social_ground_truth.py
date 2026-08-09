"""Extract social ground truth from an approved post manifest — provider-independent.

Replaces `extract_social_ground_truth_with_manus.py` (UX-P028, #1497). Manus is
permanently retired (Alex ruling 2026-07-31); the extraction step now runs through
the project's existing OpenAI client (`app.services.llm`), which is already the
sanctioned LLM path for classification and market hooks.

Only the MODEL CALL lives here. The contract — manifest parsing, the prompt, and
output parsing with poison isolation — is pure and lives in
`app.utils.social_ground_truth_extraction`, so it can be frozen in fixtures and
replayed without a network.

This script does not scrape Instagram. Give it post URLs, captions, OCR text or
public image URLs captured by an approved/manual workflow.

Usage:
    OPENAI_API_KEY=... python3 scripts/extract_social_ground_truth.py posts.jsonl --output /tmp/social_gt.review.jsonl
    python3 scripts/extract_social_ground_truth.py posts.csv --dry-run --prompt-output /tmp/prompt.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.social_ground_truth_extraction import (  # noqa: E402
    EXTRACTOR_VERSION,
    REVIEW_FIELDS,
    ExtractionUnavailable,
    build_extraction_prompt,
    load_post_manifest,
    parse_extraction_output,
)

DEFAULT_MODEL = "gpt-4o-mini"
# The manifest is inlined in the prompt and the reply is one JSON object per
# market, so the reply is bounded by post count, not by model verbosity.
DEFAULT_MAX_TOKENS = 4000


def extract_rows(
    posts: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, object]:
    """Run extraction against the configured provider.

    Raises ``ExtractionUnavailable`` when no provider is configured — a dead
    provider must be loud, not an empty success.
    """
    from app.services import llm

    client = llm._get_client()
    if client is None:
        raise ExtractionUnavailable(
            "No LLM provider configured (OPENAI_API_KEY unset or openai package "
            "missing); refusing to report an empty extraction as success."
        )

    prompt = build_extraction_prompt(posts)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract prediction-market ground truth and reply with "
                    "JSONL only. No prose, no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        # Deterministic: the same manifest must extract to the same rows, or
        # "replay is idempotent" is not a property this pipeline has.
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    return parse_extraction_output(content, extractor_version=EXTRACTOR_VERSION)


def write_review_jsonl(rows: list[dict[str, str]], output_path: str | Path) -> None:
    output = sys.stdout if str(output_path) == "-" else Path(output_path).open("w")
    close = output is not sys.stdout
    try:
        for row in rows:
            output.write(json.dumps({field: row.get(field, "") for field in REVIEW_FIELDS}))
            output.write("\n")
    finally:
        if close:
            output.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="CSV, JSON, or JSONL approved post manifest")
    parser.add_argument("--output", default="-", help="Review JSONL output path")
    parser.add_argument("--prompt-output", default=None, help="Write the prompt to a file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Build the prompt but call no provider"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument(
        "--rejected-output",
        default=None,
        help="Write isolated malformed rows here (JSONL) instead of only counting them",
    )
    args = parser.parse_args(argv)

    posts = load_post_manifest(args.manifest)
    if args.prompt_output:
        Path(args.prompt_output).write_text(build_extraction_prompt(posts))
    if args.dry_run:
        print(build_extraction_prompt(posts))
        return 0

    result = extract_rows(posts, model=args.model, max_tokens=args.max_tokens)
    rows = list(result["rows"])  # type: ignore[arg-type]
    rejected = list(result["rejected"])  # type: ignore[arg-type]

    write_review_jsonl(rows, args.output)
    if rejected:
        # Visible on stderr even when rows go to stdout — isolation is only
        # useful if somebody can see it happened.
        print(
            f"[{EXTRACTOR_VERSION}] isolated {len(rejected)} malformed row(s)",
            file=sys.stderr,
        )
        if args.rejected_output:
            with Path(args.rejected_output).open("w") as handle:
                for row in rejected:
                    handle.write(json.dumps(row))
                    handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
