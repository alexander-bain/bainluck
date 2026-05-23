from app.utils.feed_quality_debug import diagnose_feed_items


def test_diagnose_feed_items_exposes_snapshot_fields_for_futures():
    item = {
        "type": "futures",
        "score": 82,
        "headline": "A clear AI product race",
        "reason": "Yes leads at 61%",
        "data": {
            "id": 123,
            "name": "Will OpenAI release GPT-5 before July?",
            "source": "polymarket",
            "llm_sport_category": "tech",
            "image_url": "https://example.com/image.jpg",
            "hook_description": "A concrete product-launch market",
            "group_id": "story:ai",
            "top_outcomes": [
                {"name": "Yes", "probability": 0.61},
                {"name": "No", "probability": 0.39},
            ],
        },
    }

    diagnosed = diagnose_feed_items([item])

    assert diagnosed[0]["context"] == "A clear AI product race"
    assert diagnosed[0]["hook_description"] == "A concrete product-launch market"
    assert diagnosed[0]["image_url"] == "https://example.com/image.jpg"
    assert diagnosed[0]["group_id"] == "story:ai"
    assert diagnosed[0]["top_outcomes"] == item["data"]["top_outcomes"]
    assert diagnosed[0]["rendered_probability"] == 0.61
