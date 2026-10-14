import json
import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError, RateLimited
from app.core.logging import JsonFormatter, redact
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.core.rate_limit import RateLimiter
from app.schemas.clients import ClientCreate
from app.schemas.projects import ProjectCreate


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_blocks_after_limit_and_resets_after_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock)
    for _ in range(3):
        limiter.hit("k", 3, 60)
    with pytest.raises(RateLimited) as exc:
        limiter.hit("k", 3, 60)
    assert exc.value.headers and int(exc.value.headers["Retry-After"]) >= 1
    limiter.hit("other", 3, 60)  # keys are independent
    clock.now = 61
    limiter.hit("k", 3, 60)  # new window


def test_cursor_round_trip_and_tampering() -> None:
    cursor = encode_cursor(["acme", "6a1d0d6e-2f4c-4f61-9e3e-2b0f5d1c9e7a"])
    assert decode_cursor(cursor, 2) == ["acme", "6a1d0d6e-2f4c-4f61-9e3e-2b0f5d1c9e7a"]
    for bad in ["%%%", encode_cursor(["only-one"]), "eyJ4IjoxfQ"]:
        with pytest.raises(AppError):
            decode_cursor(bad, 2)
    with pytest.raises(AppError):
        cursor_uuid("nope")


def test_redaction_of_sensitive_keys() -> None:
    data = {"email": "a@b.c", "password": "x", "nested": {"refresh_token": "y", "list": [{"Authorization": "z"}]}}
    assert redact(data) == {
        "email": "a@b.c",
        "password": "[REDACTED]",
        "nested": {"refresh_token": "[REDACTED]", "list": [{"Authorization": "[REDACTED]"}]},
    }


def test_json_log_line_redacts_extra_data() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.data = {"password": "hunter2"}
    line = json.loads(JsonFormatter().format(record))
    assert line["msg"] == "hello" and line["data"]["password"] == "[REDACTED]"
    assert "hunter2" not in json.dumps(line)


def test_production_requires_strong_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="dev-only-insecure-secret-change-me-please-0000")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="short")  # type: ignore[arg-type]
    ok = Settings(environment="production", jwt_secret="x" * 40)  # type: ignore[arg-type]
    assert ok.is_production


@pytest.mark.parametrize("value", ["85", "85.5", "85.50", "0", "0.01"])
def test_money_accepts_decimal_strings(value: str) -> None:
    dumped = ClientCreate(name="A", default_hourly_rate=value).model_dump(mode="json")  # type: ignore[arg-type]
    assert dumped["default_hourly_rate"].count(".") == 1 and len(dumped["default_hourly_rate"].split(".")[1]) == 2


@pytest.mark.parametrize("value", [85.5, 85, "85.555", "-1", "1e3", "", "abc", "100000000"])
def test_money_rejects_floats_and_bad_strings(value: object) -> None:
    with pytest.raises(ValidationError):
        ClientCreate(name="A", default_hourly_rate=value)  # type: ignore[arg-type]


def test_color_is_normalised_and_validated() -> None:
    p = ProjectCreate(client_id="6a1d0d6e-2f4c-4f61-9e3e-2b0f5d1c9e7a", name="X", color="#abcdef")  # type: ignore[arg-type]
    assert p.color == "#ABCDEF"
    with pytest.raises(ValidationError):
        ProjectCreate(client_id="6a1d0d6e-2f4c-4f61-9e3e-2b0f5d1c9e7a", name="X", color="red")  # type: ignore[arg-type]
