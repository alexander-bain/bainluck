"""Bain Luck backend application."""

# #12433: before any module of the app can make a request, no log record can
# carry a credential query value (StatPal's access_key) in any process.
from app.log_redaction import install_log_redaction as _install_log_redaction

_install_log_redaction()
