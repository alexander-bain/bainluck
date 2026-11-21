"""One metered picture from a fixed, text-only template."""

import base64
import binascii
from datetime import timedelta
import json
import os
import re
import shutil
import subprocess
from urllib.request import Request, urlopen

from model import PACIFIC, STATIONS, instant
from notes import COLLECTOR_DAILY_CALLS, LABELS, MONTHLY_COST_MICROS
from signals import on_floor
from llm_models import UnsupportedModelError, image_model_for_task

DAILY_PICTURE_ENABLED = False
MEASUREMENT_MONTH_MICROS = 5_000_000
MEASUREMENT_MAX_MICROS = 500_000
SIZE = "1024x1024"
QUALITY = "medium"
MAX_PROMPT_BYTES = 2048
# The provider calculator gives the fixed-resolution output estimate. Reserve
# over four times its 823 tokens, plus the entire ASCII byte count of the prompt.
OUTPUT_TOKEN_RESERVE = 4096
MAX_WEBP_BYTES = 512_000
ASSET_NAME = re.compile(r"factory-picture-(\d{4}-\d{2}-\d{2})\.webp\Z")
ASSET_LABEL = re.compile(r"v1\|([0-9TZ:.+\-]+)\|(\d{1,6})\|(\d{1,6})\Z")


def quote(spec):
    return {
        "tool": spec.model,
        "size": SIZE,
        "quality": QUALITY,
        "reserve_micros": (
            MAX_PROMPT_BYTES * spec.text_input_per_m
            + OUTPUT_TOKEN_RESERVE * spec.image_output_per_m
        ),
        "rates": spec.price_url,
    }


def picture_request(snapshot, spec):
    through = instant(snapshot["generated_at"])
    day = through.astimezone(PACIFIC).date().isoformat()
    changes = snapshot["changes"]
    live = [
        change for change in changes if change["station"] == "Live"
        and change.get("live_at")
        and instant(change["live_at"]).astimezone(PACIFIC).date().isoformat() == day
    ]
    active = [change for change in changes if on_floor(change)]
    facts = {
        "changes_on_the_floor": len({change["number"] for change in active}),
        "changes_live_today": len({change["number"] for change in live}),
        "crates_by_station": {
            LABELS[station]: sum(change["station"] == station for change in active + live)
            for station in STATIONS
        },
        "server_dock_on_hold": any(
            stop["kind"] == "hold" and stop["line"] == "Server"
            for stop in snapshot.get("stops", [])
        ),
    }
    prompt = (
        "Draw one friendly cartoon copper and enamel workshop on cream paper. "
        "Use hand-inked outlines, simple shapes, stacked wooden crates and warm lamps. "
        "Show its morning-to-evening work as a single shop-floor scene. Use the facts "
        "for how busy the benches, checks, inspection, and loading dock look. "
        "An empty station stays empty. Use no lettering, digits, logos, signatures, "
        "watermarks or realistic people. All signs and surfaces are blank. "
        "The caption is set outside the picture. Recorded facts: "
        + json.dumps(facts, sort_keys=True, ensure_ascii=True)
    )
    if len(prompt.encode("ascii")) > MAX_PROMPT_BYTES:
        raise ValueError("The Factory picture prompt exceeds its cost reserve")
    record = {
        "day": day, "as_of": snapshot["generated_at"],
        "floor": facts["changes_on_the_floor"], "shipped": facts["changes_live_today"],
    }
    return record, {
        "model": spec.model, "prompt": prompt, "n": 1, "size": SIZE,
        "quality": QUALITY, "complexity": "low", "background": "opaque",
        "output_format": "webp", "output_compression": 80,
    }


def asset_name(record):
    return f"factory-picture-{record['day']}.webp"


def asset_label(record):
    return f"v1|{record['as_of']}|{record['floor']}|{record['shipped']}"


def gallery(assets, now):
    today = now.astimezone(PACIFIC).date()
    records = {}
    for asset in assets:
        name = ASSET_NAME.fullmatch(asset.get("name") or "")
        label = ASSET_LABEL.fullmatch(asset.get("label") or "")
        if not name or not label or asset.get("state") != "uploaded":
            continue
        try:
            at = instant(label[1])
            day = at.astimezone(PACIFIC).date()
        except (ValueError, TypeError):
            continue
        if day > today or at > now or day.isoformat() != name[1]:
            continue
        records[name[1]] = {
            "day": name[1], "as_of": label[1], "floor": int(label[2]), "shipped": int(label[3]),
        }
    recent = [records[day] for day in sorted(records, reverse=True)]
    return [
        record for record in recent
        if instant(record["as_of"]).astimezone(PACIFIC).date() >= today - timedelta(days=6)
    ] or recent[:1]


def request_image(payload, key):
    request = Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=50) as reply:
        body = reply.read(2_000_000)
        return json.loads(body), reply.headers.get("x-request-id")


def image_usage(response, spec):
    usage = response["usage"]
    inputs = usage["input_tokens_details"]
    image = usage["output_tokens"]
    if "output_tokens_details" in usage:
        details = usage["output_tokens_details"]
        if details.get("text_tokens", 0) or details["image_tokens"] != image:
            raise ValueError("Unpriced Factory picture output")
    tokens = {
        "input_text": inputs["text_tokens"], "input_image": inputs["image_tokens"],
        "output_image": image,
    }
    if (any(type(value) is not int or value < 0 for value in tokens.values())
        or tokens["input_text"] + tokens["input_image"] != usage["input_tokens"]
        or image == 0):
        raise ValueError("Incomplete Factory picture usage")
    spent = (
        tokens["input_text"] * spec.text_input_per_m
        + tokens["input_image"] * spec.image_input_per_m
        + tokens["output_image"] * spec.image_output_per_m
    )
    return tokens, spent


def picture_bytes(response):
    images = response["data"]
    if len(images) != 1:
        raise ValueError("Expected exactly one Factory picture")
    content = base64.b64decode(images[0]["b64_json"], validate=True)
    if (not 12 < len(content) <= MAX_WEBP_BYTES
        or content[:4] != b"RIFF" or content[8:12] != b"WEBP"):
        raise ValueError("The Factory picture is outside the WebP size limit")
    return content


def prepare_text_check():
    if not shutil.which("tesseract") and os.environ.get("GITHUB_ACTIONS") == "true":
        # Install only on an eligible evening. The subprocess needs no secrets.
        subprocess.run(
            ["sudo", "-n", "apt-get", "-qq", "install", "-y",
             "--no-install-recommends", "tesseract-ocr"],
            env={"PATH": os.defpath, "DEBIAN_FRONTEND": "noninteractive"},
            capture_output=True, timeout=40, check=True,
        )
    return bool(shutil.which("tesseract"))


def no_lettering(content):
    result = subprocess.run(
        [shutil.which("tesseract") or "tesseract", "stdin", "stdout", "--psm", "11"],
        input=content, capture_output=True, timeout=10, check=True, env={"PATH": os.defpath},
    )
    return not re.search(rb"[A-Za-z0-9]", result.stdout)


def metered_picture(snapshot, budget, key, *, sample=False, enabled=DAILY_PICTURE_ENABLED,
                    request=request_image, prepare=prepare_text_check, check=no_lettering):
    if not sample and not enabled:
        return None, {"status": "off"}
    now = budget.now
    meter = budget.state()
    local = now.astimezone(PACIFIC)
    mode = "sample" if sample else "daily"
    if (not key or not meter or not budget.save or not snapshot
        or not timedelta(0) <= now - instant(snapshot["generated_at"]) <= timedelta(minutes=15)):
        return None, {"status": "input-unavailable", "mode": mode}
    if sample and (enabled or meter.get("picture_sample")):
        return None, {"status": "sample-unavailable", "mode": mode}
    if not sample and (local.hour < 18 or meter.get("picture_day") == local.date().isoformat()):
        return None, {"status": "outside-daily-turn"}

    try:
        spec = image_model_for_task("factory_picture")
        record, payload = picture_request(snapshot, spec)
    except (UnsupportedModelError, ValueError):
        return None, {"status": "unpriced", "mode": mode}
    receipt = {**quote(spec), "mode": mode}
    reserve = receipt["reserve_micros"]
    if sample and (reserve > MEASUREMENT_MAX_MICROS
                   or meter["month_micros"] + reserve > MEASUREMENT_MONTH_MICROS):
        return None, {**receipt, "status": "over-measurement-budget"}
    if meter["calls"] >= COLLECTOR_DAILY_CALLS or meter["month_micros"] + reserve > MONTHLY_COST_MICROS:
        return None, {**receipt, "status": "no-reservation"}
    try:
        if not sample and not prepare():
            return None, {**receipt, "status": "text-check-unavailable"}
    except (OSError, subprocess.SubprocessError):
        return None, {**receipt, "status": "text-check-unavailable"}
    reservation = budget.reserve(
        reserve, picture=mode, month_limit=MEASUREMENT_MONTH_MICROS if sample else None,
    )
    if not reservation:
        return None, {**receipt, "status": "no-reservation"}
    try:
        response, request_id = request(payload, key)
        tokens, spent = image_usage(response, spec)
    except Exception:
        # The reservation survives errors where chargeable usage is unknown.
        return None, {**receipt, "status": "usage-unavailable", **budget.stats()}
    receipt.update(tokens=tokens, used_micros=spent)
    if request_id and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        receipt["request_id"] = request_id
    try:
        budget.settle(reservation, spent)
    except Exception:
        return None, {**receipt, "status": "reservation-retained", **budget.stats()}
    receipt.update(budget.stats())
    receipt["tokens_in"] = tokens["input_text"] + tokens["input_image"]
    receipt["tokens_out"] = tokens["output_image"]
    if spent > reserve:
        return None, {**receipt, "status": "price-over-reservation"}
    try:
        content = picture_bytes(response)
        if sample:
            # A measurement reserves and reconciles cost only.
            return None, {**receipt, "status": "measured"}
        if check(content):
            return (record, content), {**receipt, "status": "drawn"}
    except (ValueError, KeyError, TypeError, binascii.Error, OSError, subprocess.SubprocessError):
        pass
    return None, {**receipt, "status": "picture-unusable"}


if __name__ == "__main__":
    print(json.dumps(quote(image_model_for_task("factory_picture"))))
