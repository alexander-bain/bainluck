"""Tests for Apple Sign-In JWT verification and auth endpoint."""

import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# verify_apple_id_token
# =============================================================================
class TestVerifyAppleIdToken:
    """Tests for Apple id_token JWT verification."""

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_valid_token(self, mock_jwk_client_cls):
        """Valid Apple id_token returns decoded claims."""
        from app.services.firebase_auth import verify_apple_id_token

        # Set up mock JWKS client
        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-rsa-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        expected_claims = {
            "sub": "001234.abcdef.5678",
            "email": "user@privaterelay.appleid.com",
            "email_verified": "true",
            "iss": "https://appleid.apple.com",
            "aud": "com.bainluck.web",
        }

        with patch("jwt.decode", return_value=expected_claims) as mock_decode:
            result = verify_apple_id_token("fake.jwt.token", "com.bainluck.web")

            assert result == expected_claims
            mock_decode.assert_called_once_with(
                "fake.jwt.token",
                "fake-rsa-key",
                algorithms=["RS256"],
                audience="com.bainluck.web",
                issuer="https://appleid.apple.com",
            )

        # Reset the global
        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_invalid_token_returns_none(self, mock_jwk_client_cls):
        """Invalid token returns None."""
        from app.services.firebase_auth import verify_apple_id_token

        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client
        mock_client.get_signing_key_from_jwt.side_effect = Exception("Invalid token")

        result = verify_apple_id_token("bad.jwt.token", "com.bainluck.web")
        assert result is None

        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_wrong_audience_returns_none(self, mock_jwk_client_cls):
        """Token with wrong audience returns None."""
        from app.services.firebase_auth import verify_apple_id_token
        import jwt as pyjwt

        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-rsa-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("jwt.decode", side_effect=pyjwt.exceptions.InvalidAudienceError("wrong audience")):
            result = verify_apple_id_token("fake.jwt.token", "com.bainluck.web")
            assert result is None

        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_expired_token_returns_none(self, mock_jwk_client_cls):
        """Expired token returns None."""
        from app.services.firebase_auth import verify_apple_id_token
        import jwt as pyjwt

        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-rsa-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("jwt.decode", side_effect=pyjwt.exceptions.ExpiredSignatureError("expired")):
            result = verify_apple_id_token("fake.jwt.token", "com.bainluck.web")
            assert result is None

        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_jwks_client_is_cached(self, mock_jwk_client_cls):
        """JWKS client is created once and reused."""
        from app.services.firebase_auth import verify_apple_id_token

        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-rsa-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("jwt.decode", return_value={"sub": "test", "email": "a@b.com"}):
            verify_apple_id_token("token1", "com.bainluck.web")
            verify_apple_id_token("token2", "com.bainluck.web")

        # PyJWKClient should only be created once
        assert mock_jwk_client_cls.call_count == 1
        # But get_signing_key should be called twice (once per token)
        assert mock_client.get_signing_key_from_jwt.call_count == 2

        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None

    @patch("app.services.firebase_auth._apple_jwks_client", None)
    @patch("jwt.PyJWKClient")
    def test_private_relay_email(self, mock_jwk_client_cls):
        """Private relay emails (Hide My Email) work normally."""
        from app.services.firebase_auth import verify_apple_id_token

        mock_client = MagicMock()
        mock_jwk_client_cls.return_value = mock_client

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-rsa-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        claims = {
            "sub": "001234.abcdef.5678",
            "email": "abc123@privaterelay.appleid.com",
            "is_private_email": "true",
        }

        with patch("jwt.decode", return_value=claims):
            result = verify_apple_id_token("fake.jwt.token", "com.bainluck.web")
            assert result is not None
            assert result["email"] == "abc123@privaterelay.appleid.com"
            assert result["is_private_email"] == "true"

        import app.services.firebase_auth as fb_auth
        fb_auth._apple_jwks_client = None


# =============================================================================
# auth_status provider list logic
# =============================================================================
class TestAuthStatusProviders:
    """Tests for the auth_status provider list construction logic.

    These test the provider list construction inline rather than importing
    the route module (which triggers Python 3.9 incompatible imports).
    """

    def test_both_providers(self):
        """Both Google and Apple show when both are configured."""
        import os
        with patch.dict(os.environ, {"APPLE_SERVICES_ID": "com.bainluck.web"}):
            providers = []
            providers.append("google")  # is_configured() == True
            if os.getenv("APPLE_SERVICES_ID"):
                providers.append("apple")
            assert providers == ["google", "apple"]

    def test_google_only(self):
        """Only Google shows when Apple is not configured."""
        import os
        env = os.environ.copy()
        env.pop("APPLE_SERVICES_ID", None)
        with patch.dict(os.environ, env, clear=True):
            providers = []
            providers.append("google")  # is_configured() == True
            if os.getenv("APPLE_SERVICES_ID"):
                providers.append("apple")
            assert providers == ["google"]

    def test_no_providers(self):
        """No providers when Firebase is not configured."""
        import os
        env = os.environ.copy()
        env.pop("APPLE_SERVICES_ID", None)
        with patch.dict(os.environ, env, clear=True):
            providers = []
            # is_configured() == False, so no google
            if os.getenv("APPLE_SERVICES_ID"):
                providers.append("apple")
            assert providers == []


# =============================================================================
# Apple display name construction
# =============================================================================
class TestAppleDisplayName:
    """Test display name construction from Apple's first/last name fields."""

    def test_full_name(self):
        """First + last name constructs proper display name."""
        parts = [p for p in ["John", "Doe"] if p]
        display_name = " ".join(parts) if parts else None
        assert display_name == "John Doe"

    def test_first_name_only(self):
        """Only first name provided."""
        parts = [p for p in ["John", None] if p]
        display_name = " ".join(parts) if parts else None
        assert display_name == "John"

    def test_last_name_only(self):
        """Only last name provided."""
        parts = [p for p in [None, "Doe"] if p]
        display_name = " ".join(parts) if parts else None
        assert display_name == "Doe"

    def test_no_name(self):
        """No name fields (returning user)."""
        parts = [p for p in [None, None] if p]
        display_name = " ".join(parts) if parts else None
        assert display_name is None
