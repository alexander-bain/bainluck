from scripts.evals.range_card_distribution_truth_contract import decide, display, evaluate, load


def _case(case_id):
    return next(case for case in load()["cases"] if case["id"] == case_id)


def test_committed_corpus_matches_oracle():
    report = evaluate(load())
    assert report["total"] == 19
    assert report["passed"] == report["total"], report["cases"]


def test_named_specimens_do_not_render_as_truth():
    assert decide(_case("spacex-eight-half-defaults"))["verdict"] == "withhold"
    assert decide(_case("netflix-244-percent"))["verdict"] == "refuse"


def test_structure_prevents_false_normalization():
    assert decide(_case("valid-exclusive"))["verdict"] == "render"
    assert decide(_case("independent-binaries-control"))["verdict"] == "render"
    assert decide(_case("cumulative-ladder-decoy"))["verdict"] == "render"
    assert decide(_case("unknown-structure"))["verdict"] == "refuse"


def test_text_fill_and_track_geometry_share_one_contract():
    assert display(_case("absolute-fill-honest"))["verdict"] == "render"
    assert display(_case("leader-relative-fill-lies"))["verdict"] == "refuse"
    assert display(_case("unequal-label-tracks"))["verdict"] == "refuse"
