"""Opaque keyset cursors: base64url(JSON list of the last row's sort key)."""

import base64
import binascii
import json
import uuid
from typing import Any

from app.core.errors import AppError

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps([str(v) for v in values], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, size: int) -> list[str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise AppError("Malformed cursor.", code="BAD_REQUEST") from exc
    if not isinstance(values, list) or len(values) != size or not all(isinstance(v, str) for v in values):
        raise AppError("Malformed cursor.", code="BAD_REQUEST")
    return values


def cursor_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError("Malformed cursor.", code="BAD_REQUEST") from exc
