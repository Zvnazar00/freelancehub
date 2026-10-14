import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core import security
from app.core.config import Settings


@pytest.fixture
def cfg() -> Settings:
    return Settings(jwt_secret="unit-test-secret-long-enough-0123456789abcdef")  # type: ignore[arg-type]


def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = security.hash_password("s3cret-password")
    assert hashed.startswith("$argon2id$")
    assert "s3cret-password" not in hashed
    assert security.verify_password(hashed, "s3cret-password")
    assert not security.verify_password(hashed, "wrong-password")


def test_verify_password_handles_missing_and_garbage_hashes() -> None:
    assert not security.verify_password(None, "anything")
    assert not security.verify_password("not-a-hash", "anything")


def test_access_token_round_trip(cfg: Settings) -> None:
    uid, sid = uuid.uuid4(), uuid.uuid4()
    claims = security.decode_access_token(security.create_access_token(uid, sid, cfg), cfg)
    assert claims.user_id == uid and claims.session_id == sid


def test_expired_access_token(cfg: Settings) -> None:
    token = security.create_access_token(uuid.uuid4(), uuid.uuid4(), cfg, now=datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(security.TokenError) as exc:
        security.decode_access_token(token, cfg)
    assert exc.value.code == "TOKEN_EXPIRED"


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda c: jwt.encode({"sub": str(uuid.uuid4())}, "other-secret-0123456789-0123456789", algorithm="HS256"),
        lambda c: jwt.encode(
            {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "refresh", "iat": 0, "exp": 9999999999},
            c.jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),
        lambda c: jwt.encode(
            {"sub": "not-a-uuid", "sid": str(uuid.uuid4()), "type": "access", "iat": 0, "exp": 9999999999},
            c.jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),
        lambda c: "garbage.token.value",
        # "none" algorithm must never be accepted
        lambda c: jwt.encode(
            {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "access", "iat": 0, "exp": 9999999999},
            None,
            algorithm="none",
        ),
    ],
    ids=["wrong-secret", "wrong-type", "bad-sub", "garbage", "alg-none"],
)
def test_invalid_access_tokens(cfg: Settings, token_factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(security.TokenError) as exc:
        security.decode_access_token(token_factory(cfg), cfg)
    assert exc.value.code == "TOKEN_INVALID"


def test_refresh_tokens_are_random_and_hashed() -> None:
    a, b = security.generate_refresh_token(), security.generate_refresh_token()
    assert a != b and len(a) >= 43
    assert security.hash_refresh_token(a) == security.hash_refresh_token(a)
    assert len(security.hash_refresh_token(a)) == 64 and a not in security.hash_refresh_token(a)
