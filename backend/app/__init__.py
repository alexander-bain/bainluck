"""Bain Luck backend application."""

# #12433: before any module of the app can make a request, the HTTP client's
# request log stops printing credential query values (StatPal's access_key).
from app.log_redaction import install_http_client_log_redaction as _install_redaction

_install_redaction()
