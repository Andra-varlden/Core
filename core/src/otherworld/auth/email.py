"""Magic-link delivery. See About/plan.md M6.

Falls back to logging the link instead of sending it whenever
`settings.resend_api_key` is unset — auth is fully testable and usable in
local dev without a Resend account. The call site (`auth.service.
request_magic_link`) never changes either way; only this function's
behaviour does, once a real key is set in the deployed environment (see
README.deploy.md). Uses stdlib `urllib` rather than adding an HTTP client
dependency for a single, rarely-hot-path API call.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from otherworld.config import settings

logger = logging.getLogger("otherworld.auth.email")

_RESEND_URL = "https://api.resend.com/emails"
_FROM_ADDRESS = "Otherworld <login@otherworld.example>"  # [TUNE] replace once a real sending domain exists


def send_magic_link(email: str, link_url: str) -> None:
    if not settings.resend_api_key:
        logger.warning("DEV MODE (no RESEND_API_KEY set) — magic link for %s: %s", email, link_url)
        return

    body = json.dumps(
        {
            "from": _FROM_ADDRESS,
            "to": [email],
            "subject": "Your Otherworld sign-in link",
            "html": f'<p>Click to sign in: <a href="{link_url}">{link_url}</a></p>'
            f"<p>This link expires in 15 minutes.</p>",
        }
    ).encode()
    request = urllib.request.Request(
        _RESEND_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 400:
                logger.error("Resend returned %s sending to %s", response.status, email)
    except urllib.error.URLError:
        logger.exception("failed to send magic link to %s", email)
