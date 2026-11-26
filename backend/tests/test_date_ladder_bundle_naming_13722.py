"""Regression tests for #13722: date-ladder bundle members keep open names."""

from app.utils.discover_bundles import _public_member_item


def test_date_ladder_bundle_member_never_stamps_past_or_single_date():
    iran_ceasefire = {
        "type": "futures",
        "score": 84.0,
        "_raw_market_name": "US x Iran Effective Ceasefire begins by...? (2 week pause)",
        "reason": "",
        "data": {
            "id": 69603905,
            "name": "US x Iran Effective Ceasefire begins? (2 week pause)",
            "top_outcomes": [
                {"id": 1, "name": "December 31", "probability": 0.885},
                {"id": 2, "name": "November 30", "probability": 0.765},
                {"id": 3, "name": "November 22", "probability": 0.575},
            ],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "November 22", "value": 1.0, "probability": 0.575, "source": "date_bucket"},
                    {"label": "November 30", "value": 2.0, "probability": 0.765, "source": "date_bucket"},
                    {"label": "December 31", "value": 3.0, "probability": 0.885, "source": "date_bucket"},
                ],
            },
        },
    }
    pub_iran = _public_member_item(iran_ceasefire)
    assert pub_iran["data"]["name"] == "US x Iran Effective Ceasefire begins? (2 week pause)"
    assert "November 22" not in pub_iran["data"]["name"]
    assert "title_states_single_answer" not in pub_iran["data"]


def test_date_ladder_russia_ukraine_keeps_open_name_over_12_date_buckets():
    ru_ceasefire = {
        "type": "futures",
        "score": 82.0,
        "_raw_market_name": "Russia x Ukraine ceasefire agreement by ___?",
        "reason": "",
        "data": {
            "id": 20569379,
            "name": "Russia x Ukraine ceasefire agreement?",
            "top_outcomes": [
                {"id": 1, "name": "December 31, 2027", "probability": 0.68},
                {"id": 2, "name": "November 30, 2027", "probability": 0.68},
                {"id": 3, "name": "October 31, 2027", "probability": 0.67},
            ],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "May 31, 2027", "value": 6.0, "probability": 0.545, "source": "date_bucket"},
                    {"label": "June 30, 2027", "value": 7.0, "probability": 0.585, "source": "date_bucket"},
                    {"label": "October 31, 2027", "value": 11.0, "probability": 0.67, "source": "date_bucket"},
                ],
            },
        },
    }
    pub_ru = _public_member_item(ru_ceasefire)
    assert pub_ru["data"]["name"] == "Russia x Ukraine ceasefire agreement?"
    assert "May 31, 2027" not in pub_ru["data"]["name"]
    assert "title_states_single_answer" not in pub_ru["data"]


def test_single_date_and_numeric_threshold_members_preserve_single_row_fill():
    single_date = {
        "type": "futures",
        "_raw_market_name": "Will Iran target Jordan by ___?",
        "data": {
            "id": 60627569,
            "name": "Will Iran target Jordan by November 30?",
            "top_outcomes": [{"id": 1, "name": "November 30", "probability": 0.095}],
            "discover_card": {"suggested_format": "binary_probability", "threshold_points": []},
        },
    }
    pub_single = _public_member_item(single_date)
    assert pub_single["data"]["name"] == "Will Iran target Jordan by November 30?"
    assert pub_single["data"].get("title_states_single_answer") is True

    numeric_ladder = {
        "type": "futures",
        "_raw_market_name": "OpenAI IPO closing market cap above ___?",
        "data": {
            "id": 999200,
            "name": "OpenAI IPO closing market cap above ___?",
            "top_outcomes": [{"id": 1, "name": "$800B", "probability": 0.58}],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "$600B", "value": 600.0, "probability": 0.72, "source": "outcome"},
                    {"label": "$800B", "value": 800.0, "probability": 0.58, "source": "outcome"},
                    {"label": "$1T", "value": 1000.0, "probability": 0.30, "source": "outcome"},
                ],
            },
        },
    }
    pub_numeric = _public_member_item(numeric_ladder)
    assert pub_numeric["data"]["name"] == "OpenAI IPO closing market cap above $800B?"
    assert pub_numeric["data"].get("title_states_single_answer") is True
