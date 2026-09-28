"""M6 scope: session token signing/verification (About/plan.md, spec.md §16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from otherworld.auth.tokens import (
    create_session_token,
    generate_magic_link_token,
    hash_token,
    verify_session_token,
)

SECRET = "test-secret"


def test_a_valid_token_verifies_to_the_same_owner_id():
    owner_id = uuid.uuid4()
    token = create_session_token(owner_id, SECRET)
    assert verify_session_token(token, SECRET) == owner_id


def test_a_token_signed_with_a_different_secret_is_rejected():
    owner_id = uuid.uuid4()
    token = create_session_token(owner_id, SECRET)
    assert verify_session_token(token, "wrong-secret") is None


def test_an_expired_token_is_rejected():
    owner_id = uuid.uuid4()
    issued_at = datetime.now(UTC) - timedelta(days=31)  # SESSION_TTL is 30 days
    token = create_session_token(owner_id, SECRET, now=issued_at)
    assert verify_session_token(token, SECRET) is None


def test_a_tampered_token_is_rejected_not_raised():
    owner_id = uuid.uuid4()
    token = create_session_token(owner_id, SECRET)
    tampered = token[:-4] + "abcd"
    assert verify_session_token(tampered, SECRET) is None


def test_garbage_input_is_rejected_not_raised():
    assert verify_session_token("not-a-real-token-at-all", SECRET) is None
    assert verify_session_token("", SECRET) is None


def test_magic_link_tokens_are_unique_and_only_the_hash_is_deterministic():
    a, b = generate_magic_link_token(), generate_magic_link_token()
    assert a != b
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != hash_token(b)
    assert hash_token(a) != a  # never store the raw token
