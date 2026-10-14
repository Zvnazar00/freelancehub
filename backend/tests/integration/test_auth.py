from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.models import RefreshToken, User
from tests.conftest import AuthedUser, register
from tests.helpers import assert_problem

API = "/api/v1"


def refresh(client: TestClient, token: str) -> Any:
    return client.post(f"{API}/auth/refresh", json={"refresh_token": token})


class TestRegister:
    def test_returns_token_pair_and_profile(self, client: TestClient) -> None:
        r = client.post(
            f"{API}/auth/register",
            json={
                "email": " Ann@Example.COM ",
                "password": "a-long-password",
                "full_name": " Ann ",
                "timezone": "Europe/Kyiv",
                "default_currency": "EUR",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["token_type"] == "bearer" and body["expires_in"] == 900
        assert body["user"]["email"] == "ann@example.com"
        assert body["user"]["full_name"] == "Ann"
        assert body["user"]["timezone"] == "Europe/Kyiv" and body["user"]["default_currency"] == "EUR"
        assert "password" not in str(body["user"]).lower()

    def test_password_is_stored_hashed(self, client: TestClient, db: Session) -> None:
        register(client, "hash@example.com", "plain-text-password")
        user = db.scalar(select(User).where(User.email == "hash@example.com"))
        assert user is not None and user.password_hash.startswith("$argon2id$")

    def test_refresh_token_is_stored_only_as_hash(self, client: TestClient, db: Session) -> None:
        u = register(client, "rt@example.com")
        stored = db.scalars(select(RefreshToken.token_hash)).all()
        assert security.hash_refresh_token(u.refresh_token) in stored
        assert u.refresh_token not in stored

    def test_duplicate_email_is_case_insensitive(self, client: TestClient) -> None:
        register(client, "dup@example.com")
        r = client.post(
            f"{API}/auth/register", json={"email": "DUP@example.com", "password": "another-password", "full_name": "X"}
        )
        assert_problem(r, 409, "EMAIL_TAKEN")

    def test_validation(self, client: TestClient) -> None:
        r = client.post(
            f"{API}/auth/register",
            json={"email": "not-an-email", "password": "short", "full_name": "", "timezone": "Mars/Base"},
        )
        body = assert_problem(r, 422, "VALIDATION_ERROR")
        assert {e["field"] for e in body["errors"]} == {"email", "password", "full_name", "timezone"}

    def test_password_equal_to_email_is_rejected(self, client: TestClient) -> None:
        r = client.post(
            f"{API}/auth/register", json={"email": "same@example.com", "password": "same@example.com", "full_name": "X"}
        )
        assert_problem(r, 422, "VALIDATION_ERROR")


class TestLogin:
    def test_success(self, client: TestClient, alice: AuthedUser) -> None:
        r = client.post(f"{API}/auth/login", json={"email": "ALICE@example.com", "password": alice.password})
        assert r.status_code == 200
        assert (
            client.get(f"{API}/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
        )

    def test_wrong_password_and_unknown_email_look_identical(self, client: TestClient, alice: AuthedUser) -> None:
        wrong = client.post(f"{API}/auth/login", json={"email": alice.email, "password": "wrong-password"})
        unknown = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
        for r in (wrong, unknown):
            assert_problem(r, 401, "INVALID_CREDENTIALS")
        assert wrong.json()["detail"] == unknown.json()["detail"]

    def test_rate_limited(self, client: TestClient, settings: Settings, alice: AuthedUser) -> None:
        settings.login_rate_limit = 3
        for _ in range(3):
            client.post(f"{API}/auth/login", json={"email": alice.email, "password": "wrong-password"})
        r = client.post(f"{API}/auth/login", json={"email": alice.email, "password": alice.password})
        assert_problem(r, 429, "RATE_LIMITED")
        assert int(r.headers["Retry-After"]) > 0


class TestAccessToken:
    def test_missing_token(self, client: TestClient) -> None:
        r = client.get(f"{API}/me")
        assert_problem(r, 401, "UNAUTHENTICATED")
        assert r.headers["WWW-Authenticate"] == "Bearer"

    def test_expired_token(self, client: TestClient, alice: AuthedUser, settings: Settings) -> None:
        import uuid

        old = security.create_access_token(
            uuid.UUID(alice.id), uuid.uuid4(), settings, now=datetime.now(UTC) - timedelta(hours=2)
        )
        assert_problem(client.get(f"{API}/me", headers={"Authorization": f"Bearer {old}"}), 401, "TOKEN_EXPIRED")

    def test_forged_token(self, client: TestClient, alice: AuthedUser) -> None:
        forged = alice.access_token[:-4] + ("AAAA" if not alice.access_token.endswith("AAAA") else "BBBB")
        assert_problem(client.get(f"{API}/me", headers={"Authorization": f"Bearer {forged}"}), 401, "TOKEN_INVALID")

    def test_refresh_token_cannot_be_used_as_access_token(self, client: TestClient, alice: AuthedUser) -> None:
        r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {alice.refresh_token}"})
        assert_problem(r, 401, "TOKEN_INVALID")

    def test_token_of_deleted_user(self, client: TestClient, alice: AuthedUser, db: Session) -> None:
        user = db.get(User, __import__("uuid").UUID(alice.id))
        db.delete(user)
        db.flush()
        assert_problem(client.get(f"{API}/me", headers=alice.headers), 401, "TOKEN_INVALID")


class TestRefresh:
    def test_rotation_issues_new_pair_and_retires_old(self, client: TestClient, alice: AuthedUser, db: Session) -> None:
        r = refresh(client, alice.refresh_token)
        assert r.status_code == 200
        new = r.json()
        assert new["refresh_token"] != alice.refresh_token
        old_row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(alice.refresh_token))
        )
        new_row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(new["refresh_token"]))
        )
        assert old_row and new_row
        assert old_row.revoked_at is not None and old_row.replaced_by_id == new_row.id
        assert old_row.family_id == new_row.family_id
        assert refresh(client, new["refresh_token"]).status_code == 200

    def test_retry_within_grace_window_is_rejected_without_killing_session(
        self, client: TestClient, alice: AuthedUser
    ) -> None:
        new = refresh(client, alice.refresh_token).json()
        assert_problem(refresh(client, alice.refresh_token), 401, "TOKEN_ROTATED")
        assert refresh(client, new["refresh_token"]).status_code == 200  # session still alive

    def test_reuse_after_grace_window_revokes_whole_family(
        self, client: TestClient, alice: AuthedUser, db: Session
    ) -> None:
        new = refresh(client, alice.refresh_token).json()
        old_row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == security.hash_refresh_token(alice.refresh_token))
        )
        assert old_row is not None
        old_row.rotated_at = datetime.now(UTC) - timedelta(minutes=5)  # simulate an attacker replaying later
        db.flush()
        assert_problem(refresh(client, alice.refresh_token), 401, "TOKEN_INVALID")
        # The legitimate client's newer token is dead too.
        assert_problem(refresh(client, new["refresh_token"]), 401, "TOKEN_INVALID")

    def test_unknown_and_expired_tokens(self, client: TestClient, alice: AuthedUser, db: Session) -> None:
        assert_problem(refresh(client, "x" * 43), 401, "TOKEN_INVALID")
        row = db.scalar(select(RefreshToken))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()
        assert_problem(refresh(client, alice.refresh_token), 401, "TOKEN_INVALID")

    def test_sessions_are_independent(self, client: TestClient, alice: AuthedUser) -> None:
        second = client.post(f"{API}/auth/login", json={"email": alice.email, "password": alice.password}).json()
        client.post(f"{API}/auth/logout", json={"refresh_token": alice.refresh_token})
        assert refresh(client, second["refresh_token"]).status_code == 200


class TestLogout:
    def test_logout_revokes_session(self, client: TestClient, alice: AuthedUser) -> None:
        rotated = refresh(client, alice.refresh_token).json()["refresh_token"]
        assert client.post(f"{API}/auth/logout", json={"refresh_token": rotated}).status_code == 204
        assert_problem(refresh(client, rotated), 401, "TOKEN_INVALID")

    def test_logout_with_unknown_token_is_silent(self, client: TestClient) -> None:
        assert client.post(f"{API}/auth/logout", json={"refresh_token": "y" * 43}).status_code == 204

    def test_logout_all(self, client: TestClient, alice: AuthedUser) -> None:
        other = client.post(f"{API}/auth/login", json={"email": alice.email, "password": alice.password}).json()
        assert client.post(f"{API}/auth/logout-all", headers=alice.headers).status_code == 204
        for token in (alice.refresh_token, other["refresh_token"]):
            assert_problem(refresh(client, token), 401, "TOKEN_INVALID")

    def test_logout_all_requires_auth(self, client: TestClient) -> None:
        assert_problem(client.post(f"{API}/auth/logout-all"), 401, "UNAUTHENTICATED")
