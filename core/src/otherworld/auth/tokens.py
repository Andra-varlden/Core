"""Session and magic-link tokens. See About/plan.md M6, About/spec.md §16
("Auth via session token").

Session tokens are HMAC-signed, not a DB-backed session table — stateless,
so there's no session storage/cleanup to build, at the cost of not being
able to revoke one before it expires (acceptable for M6; a revocation list
is a straightforward addition later if abuse shows up).

Magic-link tokens ARE DB-backed (`MagicLinkTokenORM`) because they must be
single-use and revocable the instant they're consumed — a stateless token
can't do that.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

MAGIC_LINK_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=30)


def generate_magic_link_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Only the hash is ever stored — a DB read (or leak) of the tokens
    table alone can't be used to log in as anyone."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_session_token(owner_id: uuid.UUID, secret: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    expires_at = now + SESSION_TTL
    payload = f"{owner_id}:{int(expires_at.timestamp())}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def verify_session_token(token: str, secret: str, now: datetime | None = None) -> uuid.UUID | None:
    """Returns the owner_id if the token is validly signed and unexpired,
    else None — never raises, since a forged or garbled cookie is exactly
    as unauthenticated as a missing one, not a server error.
    """
    now = now or datetime.now(UTC)
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        owner_id_str, expires_at_str, signature = decoded.rsplit(":", 2)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None

    payload = f"{owner_id_str}:{expires_at_str}"
    expected_signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        expires_at = datetime.fromtimestamp(int(expires_at_str), tz=UTC)
        owner_id = uuid.UUID(owner_id_str)
    except (ValueError, OverflowError, OSError):
        return None

    if now >= expires_at:
        return None
    return owner_id
