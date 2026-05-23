"""Tests for CAN-SPAM email compliance utilities."""

import os
import unittest

from app.utils.email_compliance import (
    EMAIL_PREF_KEYS,
    generate_unsubscribe_headers,
    generate_unsubscribe_token,
    generate_unsubscribe_url,
    get_default_email_preferences,
    merge_email_preferences,
    verify_unsubscribe_token,
)


class TestEmailComplianceTokens(unittest.TestCase):
    """Token generation and verification."""

    def setUp(self):
        # Set a known secret for deterministic tests
        os.environ["EMAIL_HMAC_SECRET"] = "test-secret-key-12345"

    def tearDown(self):
        os.environ.pop("EMAIL_HMAC_SECRET", None)

    def test_generate_token_format(self):
        token = generate_unsubscribe_token(42)
        self.assertIn(":", token)
        parts = token.split(":", 1)
        self.assertEqual(parts[0], "42")
        self.assertEqual(len(parts[1]), 64)  # SHA-256 hex digest

    def test_verify_valid_token(self):
        token = generate_unsubscribe_token(42)
        user_id = verify_unsubscribe_token(token)
        self.assertEqual(user_id, 42)

    def test_verify_invalid_token(self):
        self.assertIsNone(verify_unsubscribe_token(""))
        self.assertIsNone(verify_unsubscribe_token("no-colon"))
        self.assertIsNone(verify_unsubscribe_token("abc:def"))
        self.assertIsNone(verify_unsubscribe_token("42:wrong-signature"))

    def test_verify_tampered_user_id(self):
        token = generate_unsubscribe_token(42)
        # Change user_id portion
        tampered = "99:" + token.split(":", 1)[1]
        self.assertIsNone(verify_unsubscribe_token(tampered))

    def test_tokens_are_deterministic(self):
        t1 = generate_unsubscribe_token(42)
        t2 = generate_unsubscribe_token(42)
        self.assertEqual(t1, t2)

    def test_different_users_get_different_tokens(self):
        t1 = generate_unsubscribe_token(1)
        t2 = generate_unsubscribe_token(2)
        self.assertNotEqual(t1, t2)


class TestEmailPreferences(unittest.TestCase):
    """Email preference helpers."""

    def test_default_preferences_all_false(self):
        defaults = get_default_email_preferences()
        for key in EMAIL_PREF_KEYS:
            self.assertFalse(defaults[key])

    def test_merge_updates_known_keys(self):
        existing = {"digest": False, "bug_updates": False, "market_alerts": False}
        result = merge_email_preferences(existing, {"digest": True})
        self.assertTrue(result["digest"])
        self.assertFalse(result["bug_updates"])
        self.assertFalse(result["market_alerts"])

    def test_merge_ignores_unknown_keys(self):
        existing = {"digest": False, "bug_updates": False, "market_alerts": False}
        result = merge_email_preferences(existing, {"unknown_key": True})
        self.assertNotIn("unknown_key", result)

    def test_merge_ignores_non_boolean_values(self):
        existing = {"digest": False, "bug_updates": False, "market_alerts": False}
        result = merge_email_preferences(existing, {"digest": "yes"})
        self.assertFalse(result["digest"])

    def test_merge_with_none_existing(self):
        result = merge_email_preferences(None, {"digest": True})
        self.assertTrue(result["digest"])
        self.assertFalse(result["bug_updates"])

    def test_pref_keys_are_frozen(self):
        with self.assertRaises(AttributeError):
            EMAIL_PREF_KEYS.add("new_key")


class TestUnsubscribeUrl(unittest.TestCase):
    """URL and header generation."""

    def setUp(self):
        os.environ["EMAIL_HMAC_SECRET"] = "test-secret-key-12345"

    def tearDown(self):
        os.environ.pop("EMAIL_HMAC_SECRET", None)

    def test_url_without_pref(self):
        token = generate_unsubscribe_token(42)
        url = generate_unsubscribe_url(token)
        self.assertIn("/api/unsubscribe?token=", url)
        self.assertNotIn("&pref=", url)

    def test_url_with_pref(self):
        token = generate_unsubscribe_token(42)
        url = generate_unsubscribe_url(token, pref="digest")
        self.assertIn("&pref=digest", url)

    def test_url_ignores_unknown_pref(self):
        token = generate_unsubscribe_token(42)
        url = generate_unsubscribe_url(token, pref="fake_pref")
        self.assertNotIn("&pref=", url)

    def test_headers_contain_required_fields(self):
        token = generate_unsubscribe_token(42)
        headers = generate_unsubscribe_headers(token, pref="digest")
        self.assertIn("List-Unsubscribe", headers)
        self.assertIn("List-Unsubscribe-Post", headers)
        self.assertEqual(
            headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click"
        )
        # List-Unsubscribe should be wrapped in angle brackets
        self.assertTrue(headers["List-Unsubscribe"].startswith("<"))
        self.assertTrue(headers["List-Unsubscribe"].endswith(">"))


if __name__ == "__main__":
    unittest.main()
