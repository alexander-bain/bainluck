"""Small offline side-by-side playback of actual held-page records, not a shadow UI."""
import json
import shutil
from pathlib import Path


def render(result, out):
    for arm in ("baseline", "candidate"):
        source = Path(result[arm]["path"])
        shutil.copyfile(source/"after.png", out/(arm+"-page.png"))
    template = Path(__file__).with_name("view.html").read_text()
    # JSON is data, including when a captured label contains HTML/script text.
    data = json.dumps(result, allow_nan=False).replace("<", "\\u003c")
    (out/"index.html").write_text(template.replace("/*COMPARISON_DATA*/null", data))
