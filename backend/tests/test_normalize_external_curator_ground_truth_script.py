"""Tests for the external curator normalization helper."""

from io import StringIO

from scripts.normalize_external_curator_ground_truth import (
    build_summary,
    load_inputs,
    write_csv,
    write_jsonl,
)


def test_normalizer_loads_multiple_inputs_and_writes_canonical_csv(tmp_path):
    csv_path = tmp_path / "social.csv"
    csv_path.write_text(
        "\n".join(
            [
                "publisher,title,topic,link,platform,username,likes",
                "Curator A,Will OpenAI release GPT-6?,tech,https://example.com/a,x,@markets,100",
            ]
        )
    )
    jsonl_path = tmp_path / "newsletter.jsonl"
    jsonl_path.write_text(
        '{"source":"Curator B","name":"Will Fed cut rates?","category":"economics","platform":"newsletter"}\n'
    )

    rows = load_inputs([str(csv_path), str(jsonl_path)])
    output = StringIO()
    write_csv(rows, output)

    csv_text = output.getvalue()
    assert "source,category,name,probability,hook,url,published_at,platform,handle,engagement" in csv_text
    assert "Curator A,tech,Will OpenAI release GPT-6?" in csv_text
    assert "Curator B,economics,Will Fed cut rates?" in csv_text
    assert build_summary(rows) == {
        "rows": 2,
        "sources": {"Curator A": 1, "Curator B": 1},
        "platforms": {"newsletter": 1, "x": 1},
        "stale_after_days": 7,
    }


def test_normalizer_writes_jsonl(tmp_path):
    csv_path = tmp_path / "social.csv"
    csv_path.write_text(
        "source,name,category\nCurator,Will a hurricane make landfall?,weather\n"
    )

    rows = load_inputs([str(csv_path)])
    output = StringIO()
    write_jsonl(rows, output)

    assert '"source": "Curator"' in output.getvalue()
    assert '"name": "Will a hurricane make landfall?"' in output.getvalue()
